"""
Récupération d'articles RSS avec contournement anti-scraping.

Stratégie de fetch en cascade :
  1. Cache mémoire partagé (évite de télécharger deux fois la même URL)
  2. Requête HTTP discrète (headers identiques à un vrai Chrome)
  3. Playwright Chromium headless (si JS requis ou anti-bot détecté)
  4. Proxies publics (12ft.io, archive.ph) en cas de paywall
  5. Résumé RSS comme dernier recours

Installation :
    pip install feedparser newspaper4k requests playwright beautifulsoup4
    playwright install chromium
"""

import hashlib
import json
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse
from pathlib import Path
from stealth_requests import StealthSession
from bs4 import BeautifulSoup
import feedparser
from newspaper import Article as NewspaperArticle
import requests

from playwright.sync_api import sync_playwright

from traitements.journal import log

MODE = "dev"  # dev ou production

# ── Chargement de la configuration RSS ───────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "fluxRSS.json")

with open(FILE_PATH, "r", encoding="utf-8") as f:
    _data = json.load(f)

_actualites        = _data[0].get("actualites", {})
FLUX_TECHNOLOGIE   = _actualites.get("technologies", [])
FLUX_GEOPOLITIQUE  = _actualites.get("geopolitique", [])
FLUX_IA            = _actualites.get("ia", [])
FLUX_CYBERSECURITE = _actualites.get("cybersecurite", [])
FLUX_FRANCE        = _actualites.get("france", [])
FLUX_FINANCE       = _data[0].get("finances", [])

ALL_FLUX = [
    FLUX_TECHNOLOGIE,
    FLUX_GEOPOLITIQUE,
    FLUX_IA,
    FLUX_CYBERSECURITE,
    FLUX_FRANCE,
    # FLUX_FINANCE,
]

_CODES_PAYWALL = {401, 402, 403}
_SESSION = StealthSession()


class ErreurPaywall(Exception):
    pass


# ── ZoneBourse : article principal de la page d'accueil ──────────────────────
ZONEBOURSE_URL                     = "https://www.zonebourse.com/"
_SELECTEUR_COOKIE_ZB               = "#didomi-notice-agree-button"
_SELECTEUR_ARTICLE_PRINCIPAL_ZB    = ".c-12.cm-8.mb-m-15.pos-1.pos-m-2"
_SELECTEUR_TITRE_UNE_ZB            = ".txt-s8.px-15.mt-15.txt-align-center.my-0"

_PROFIL_ZB = Path("./storage/browser-profile")


def _date_publication_zonebourse(html: str) -> Optional[datetime]:
    """Date de la balise <meta property="article:published_time"> de la page article."""
    meta = BeautifulSoup(html, "html.parser").find("meta", property="article:published_time")
    try:
        return datetime.fromisoformat(meta["content"]) if meta else None
    except ValueError:
        return None


def _nettoyer_verrous_profil(profil_dir: Path) -> None:
    """
    Supprime les fichiers de verrou Chromium pouvant rester après un
    lancement interrompu (crash, kill -9, erreur $DISPLAY, etc.).
    Sans ça, launch_persistent_context peut se fermer immédiatement
    ('Target page, context or browser has been closed').
    """
    for nom in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profil_dir / nom
        try:
            if f.exists() or f.is_symlink():
                f.unlink()
                log.debug("[*] ZoneBourse — verrou %s supprimé", nom)
        except Exception as e:
            log.warning("[!] ZoneBourse — impossible de supprimer %s : %s", nom, e)


def _gerer_captcha_cloudflare(page) -> None:
    """
    Détecte et tente de contourner un challenge Cloudflare Turnstile,
    reprend la logique de la version JS qui fonctionne.
    """
    try:
        cf_frame = next(
            (f for f in page.frames if "cloudflare" in f.url or "challenges" in f.url),
            None,
        )
        if cf_frame:
            log.warning("[!] ZoneBourse — Captcha Cloudflare détecté, tentative de clic")
            checkbox = cf_frame.wait_for_selector(
                "input[type='checkbox'], .mark", timeout=4_000
            )
            if checkbox:
                checkbox.click()
                log.debug("[*] ZoneBourse — clic captcha effectué")
        else:
            captcha_btn = page.query_selector(
                "button:has-text('Accepter & Fermer'), "
                "button:has-text('Verify you are human'), "
                "#challenge-stage input"
            )
            if captcha_btn:
                captcha_btn.click()
                log.debug("[*] ZoneBourse — clic bouton de vérification effectué")
    except Exception:
        log.debug("[*] ZoneBourse — aucun captcha Cloudflare réactif détecté")


def _recuperer_article_principal_zonebourse() -> Optional[dict]:
    """
    Récupère le titre + contenu de l'article 'à la une' sur la page d'accueil de ZoneBourse.
    """
    titre = None
    lien = None
    html = None

    _PROFIL_ZB.mkdir(parents=True, exist_ok=True)
    _nettoyer_verrous_profil(_PROFIL_ZB)

    contexte = None

    try:
        with sync_playwright() as pw:
            contexte = pw.chromium.launch_persistent_context(
                user_data_dir=str(_PROFIL_ZB),
                headless=False,  # confirmé fonctionnel sous xvfb-run
                viewport={"width": 1920, "height": 1080},
                locale="fr-FR",
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"},
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            try:
                page = contexte.pages[0] if contexte.pages else contexte.new_page()

                # Bloque images/fonts/médias pour accélérer le chargement sur un Pi
                page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type in ("image", "font", "media")
                        else route.continue_()
                    ),
                )

                log.debug("[*] ZoneBourse — chargement page d'accueil")
                try:
                    page.goto(ZONEBOURSE_URL, wait_until="commit", timeout=90_000)
                except Exception:
                    try:
                        page.screenshot(path="debug_timeout.png", full_page=True)
                        Path("debug_timeout.html").write_text(page.content(), encoding="utf-8")
                        log.error(
                            "[!] ZoneBourse — timeout au chargement, capture dans "
                            "'debug_timeout.png' / 'debug_timeout.html'"
                        )
                    except Exception:
                        log.error("[!] ZoneBourse — timeout au chargement, capture impossible")
                    raise

                # Ne pas bloquer sur domcontentloaded si la page reste "active"
                # en arrière-plan (trackers, websockets) alors que le DOM visible
                # est déjà prêt. On tente, mais on continue en cas de timeout.
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    log.debug("[*] ZoneBourse — domcontentloaded non atteint, on continue (contenu probablement déjà présent)")

                # 1. Gestion Cloudflare (reprise de la version JS)
                log.debug("[*] ZoneBourse — vérification captcha Cloudflare")
                _gerer_captcha_cloudflare(page)

                # 2. Gestion de la bannière cookie Didomi
                try:
                    bouton_cookie = page.wait_for_selector(
                        _SELECTEUR_COOKIE_ZB, state="visible", timeout=10_000
                    )
                    if bouton_cookie:
                        bouton_cookie.click(force=True)
                        log.debug("[*] ZoneBourse — cookies acceptés")
                except Exception:
                    log.debug("[*] ZoneBourse — aucune bannière cookie détectée")

                # 3. Détection de l'article principal
                try:
                    main_article = page.wait_for_selector(
                        _SELECTEUR_ARTICLE_PRINCIPAL_ZB, timeout=15_000
                    )
                except Exception:
                    log.warning("[!] ZoneBourse — article principal introuvable")
                    return None

                if not main_article:
                    log.warning("[!] ZoneBourse — aucun article trouvé")
                    return None

                # Titre de secours pris sur le bloc de la home, au cas où le sélecteur
                # dédié serait absent sur la page article
                titre_fallback = main_article.inner_text().strip().split("\n")[0]

                # 4. Navigation vers la page d'article
                main_article.click()
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=20_000)
                except Exception:
                    log.debug("[*] ZoneBourse — domcontentloaded non atteint après clic, on continue")

                # Petite pause pour laisser le temps au contenu de se stabiliser
                page.wait_for_timeout(1_500)

                # Titre "propre" pris sur la page d'article elle-même
                try:
                    titre_el = page.wait_for_selector(_SELECTEUR_TITRE_UNE_ZB, timeout=8_000)
                    titre = titre_el.inner_text().strip() if titre_el else titre_fallback
                except Exception:
                    titre = titre_fallback

                lien = page.url
                html = page.content()
            finally:
                # Fermeture tant que Playwright tourne encore : sinon les handlers de
                # page.route() sont coupés en plein vol (CancelledError / TargetClosedError)
                try:
                    contexte.unroute_all(behavior="ignoreErrors")
                    for p_ouverte in contexte.pages:
                        p_ouverte.unroute_all(behavior="ignoreErrors")
                    contexte.close()
                    log.debug("[*] ZoneBourse — contexte fermé proprement")
                except Exception:
                    pass

    except Exception as e:
        log.error("[!] ZoneBourse — échec récupération article principal : %s", e)
        return None

    if not html or not lien:
        return None

    # Le matin, le week-end ou un jour férié, la une est encore l'article de la veille
    # au soir : on ne garde que les articles publiés aujourd'hui, sinon ils sont
    # comptés dans le résumé du jour.
    date_pub = _date_publication_zonebourse(html)
    if date_pub and date_pub.astimezone().date() < datetime.now().date():
        log.debug("[*] ZoneBourse — une du %s ignorée (pas du jour)", date_pub.strftime("%d/%m %H:%M"))
        return None

    contenu = _extraire_texte(lien, html)
    if not contenu:
        log.warning("[!] ZoneBourse — contenu vide après extraction")
        return None

    return {
        "titre":       titre,
        "lien":        lien,
        "source":      "ZoneBourse - Une",
        "description": "",
        "date_pub":    (date_pub or datetime.now(timezone.utc)).isoformat(),
        "contenu":     contenu,
    }

# ── Playwright ────────────────────────────────────────────────────────────────
_donnees_thread = threading.local()

_DOMAINES_CHARGEMENT_RAPIDE = {
    "boursedirect.fr", "boursorama.com", "fr.investing.com",
    "investing.com", "theverge.com", "cbc.ca",
}

_SELECTEURS_PAR_DOMAINE: dict[str, list[str]] = {
    "fr.investing.com": ["#article", "[class*='article']", "article"],
    "investing.com":    ["#article", "[class*='article']", "article"],
    "theverge.com":     [".duet--article--article-body-component", "article", "main"],
    "cbc.ca":           ["[class*='detail']", "[class*='story']", "article", "main"],
}

_DOMAINES_BLOQUES_IP = {"zonebourse.com"}


def _obtenir_navigateur():
    if not getattr(_donnees_thread, "navigateur", None):
        from playwright.sync_api import sync_playwright
        _donnees_thread.pw        = sync_playwright().__enter__()
        _donnees_thread.navigateur = _donnees_thread.pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
    return _donnees_thread.navigateur


def _strategie_attente(url: str) -> str:
    hote = (urlparse(url).hostname or "").removeprefix("www.")
    return "domcontentloaded" if any(hote.endswith(d) for d in _DOMAINES_CHARGEMENT_RAPIDE) else "networkidle"


def telecharger_avec_playwright(url: str, timeout_ms: int = 35_000) -> str:
    navigateur = _obtenir_navigateur()
    contexte = navigateur.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/",
        },
    )
    try:
        page = contexte.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
            Object.defineProperty(navigator, 'plugins',    { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages',  { get: () => ['fr-FR', 'fr'] });
            window.chrome = { runtime: {} };
            document.cookie = "euconsent-v2=1; path=/";
            document.cookie = "cookieconsent_status=dismiss; path=/";
        """)
        reponse = page.goto(url, wait_until=_strategie_attente(url), timeout=timeout_ms)
        if reponse and reponse.status in _CODES_PAYWALL:
            raise ErreurPaywall(f"Playwright HTTP {reponse.status} pour {url}")
        hote = (urlparse(url).hostname or "").removeprefix("www.")
        selecteurs = _SELECTEURS_PAR_DOMAINE.get(hote) or ["article", "main", ".article-body", "#content"]
        for selecteur in selecteurs:
            try:
                page.wait_for_selector(selecteur, timeout=4_000)
                break
            except Exception:
                pass
        return page.content()
    finally:
        contexte.close()


# ── Détection blocage / contenu parasite ─────────────────────────────────────
def _page_bloquee(html: str) -> bool:
    signaux = [
        "cf-browser-verification", "challenge-running", "captcha",
        "Access Denied", "bot protection", "DDoS protection",
        "Enable JavaScript", "Please verify you are a human",
    ]
    html_min = html.lower()
    return any(s.lower() in html_min for s in signaux)


def _contenu_parasite(texte: str) -> bool:
    signaux = [
        "contenus non personnalisés dépendent", "annonces non personnalisées",
        "avant de continuer vers google", "google ireland limited",
        "we use cookies to", "accept all cookies",
        "en cliquant sur accepter",
    ]
    return len(texte) < 800 and any(s in texte.lower() for s in signaux)


# ── Téléchargement HTML ───────────────────────────────────────────────────────
def telecharger_html(url: str, cache: Optional[dict] = None) -> str:
    if cache and url in cache:
        return cache[url]

    hote = (urlparse(url).hostname or "").removeprefix("www.")
    if hote in _DOMAINES_BLOQUES_IP:
        raise ValueError(f"Domaine bloqué par IP : {hote}")

    html: Optional[str] = None
    try:
        reponse = _SESSION.get(url, timeout=15)
        if reponse.status_code in _CODES_PAYWALL:
            raise ErreurPaywall(f"HTTP {reponse.status_code}")
        reponse.raise_for_status()
        html = reponse.text
        if _page_bloquee(html):
            raise ValueError("Anti-bot détecté")
    except ErreurPaywall:
        raise
    except Exception:
        html = telecharger_avec_playwright(url)

    if cache is not None and html:
        cache[url] = html
    return html


# ── Extraction texte ──────────────────────────────────────────────────────────
def _extraire_texte(url: str, html: str) -> Optional[str]:
    article = NewspaperArticle(url)
    article.download(input_html=html)
    article.parse()
    texte = article.text or ""

    hote = (urlparse(url).hostname or "").removeprefix("www.")
    if len(texte) < 200 and hote in _SELECTEURS_PAR_DOMAINE:
        soupe = BeautifulSoup(html, "html.parser")
        candidats = (
            noeud.get_text(separator=" ", strip=True)
            for selecteur in _SELECTEURS_PAR_DOMAINE[hote]
            if (noeud := soupe.select_one(selecteur))
        )
        texte = max(candidats, key=len, default=texte)

    if _contenu_parasite(texte):
        return None
    return texte if len(texte) > 80 else None


# ── Paywall proxies ───────────────────────────────────────────────────────────
def _get_proxy(url_proxy: str, timeout: int = 15) -> str:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    reponse = requests.Session().get(url_proxy, timeout=timeout, allow_redirects=True, verify=False)
    if reponse.status_code == 429:
        raise requests.HTTPError(f"429 Rate limit", response=reponse)
    reponse.raise_for_status()
    return reponse.text


def _contourner_paywall(titre: str, url: str) -> Optional[str]:
    from urllib.parse import quote
    proxies = [
        (f"https://12ft.io/proxy?q={quote(url, safe='')}", "12ft.io"),
        (f"https://archive.ph/newest/{url}",               "archive.ph"),
    ]
    for url_proxy, _ in proxies:
        try:
            html = _get_proxy(url_proxy)
            texte = _extraire_texte(url, html)
            if texte and len(texte) > 200:
                return texte
        except Exception:
            pass
    return None


def _nettoyer_resume_rss(resume_rss: str) -> Optional[str]:
    if not resume_rss:
        return None
    from html import unescape
    import re
    texte = re.sub(r"<[^>]+>", " ", unescape(resume_rss)).strip()
    texte = re.sub(r"\s+", " ", texte)
    return texte if len(texte) > 80 else None


# ── Modèles ───────────────────────────────────────────────────────────────────
def analyser_date(chaine_date: str) -> Optional[datetime]:
    for parseur in (datetime.fromisoformat, parsedate_to_datetime):
        try:
            return parseur(chaine_date)
        except Exception:
            pass
    return None


# ── Stats ─────────────────────────────────────────────────────────────────────
_stats_domaines: dict = defaultdict(lambda: {"ok": 0, "err": 0, "raisons": defaultdict(int)})
_verrou_stats = threading.Lock()


def _domaine(url: str) -> str:
    return (urlparse(url).hostname or url).removeprefix("www.")


def _enregistrer_stat(url: str, succes: bool, raison: str = "") -> None:
    d = _domaine(url)
    with _verrou_stats:
        if succes:
            _stats_domaines[d]["ok"] += 1
        else:
            _stats_domaines[d]["err"] += 1
            if raison:
                _stats_domaines[d]["raisons"][raison] += 1


def _afficher_rapport() -> None:
    """Une seule ligne listant les domaines en échec (les domaines sans erreur sont omis)."""
    echecs = sorted(
        ((d, s["ok"], s["err"]) for d, s in _stats_domaines.items() if s["err"]),
        key=lambda x: -x[2],
    )
    if echecs:
        log.info("Échecs par domaine : " + ", ".join(f"{d} {err}/{ok + err}" for d, ok, err in echecs))


# ── Phase 1 : récupération des titres RSS ────────────────────────────────────
def _recuperer_titres_flux(elements: list[dict]) -> list[dict]:
    """Récupère les titres RSS d'une liste de sources, sans télécharger le contenu."""
    articles = []
    for element in elements:
        try:
            flux = feedparser.parse(element["lien"])
        except Exception:
            continue
        
        source = element.get("source") or (urlparse(element["lien"]).hostname or element["lien"])

        for entree in flux.entries:
            try:
                titre    = entree.get("title", "Sans titre")
                lien     = entree.get("link", "")
                desc     = (
                    entree.get("summary")
                    or entree.get("description")
                    or entree.get("content", [{}])[0].get("value", "")
                    or ""
                )
                if not lien:
                    continue

                
                date_pub = entree.get("published") or entree.get("updated") or ""

                dt = analyser_date(date_pub)

                if dt is None:
                    continue

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                maintenant = datetime.now(timezone.utc)

                if MODE == "production":
                    limite = (maintenant - timedelta(days=1)).replace(
                        hour=6,
                        minute=1,
                        second=0,
                        microsecond=0
                    )

                    if dt < limite or dt > maintenant:
                        continue

                elif MODE == "dev":
                    hier = (maintenant - timedelta(days=1)).date()

                    if dt.date() != hier:
                        continue

                articles.append({
                    "titre":       titre,
                    "lien":        lien,
                    "source":      source,
                    "description": desc,
                    "date_pub":    date_pub,
                })
            except Exception:
                continue
    return articles


def recuperer_articles_du_jour() -> list[dict]:
    """
    Phase 1 — Parse tous les flux RSS en parallèle, + article principal ZoneBourse.
    Retourne les articles du jour sous forme de list[dict].
    Aucun contenu n'est téléchargé pour les flux RSS classiques à ce stade
    (sauf ZoneBourse, dont le contenu est déjà inclus).
    """
    tous = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futurs = {executor.submit(_recuperer_titres_flux, flux): "rss" for flux in ALL_FLUX}
        futurs[executor.submit(_recuperer_article_principal_zonebourse)] = "zonebourse"

        for futur in as_completed(futurs):
            type_tache = futurs[futur]
            try:
                resultat = futur.result()
                if type_tache == "zonebourse":
                    if resultat:
                        tous.append(resultat)
                else:
                    tous.extend(resultat)
            except Exception as e:
                log.error("Erreur récupération flux (%s) : %s", type_tache, e)

    return tous

# ── Phase 2 : téléchargement des articles sélectionnés ───────────────────────
def _telecharger_article(article: dict, cache: dict) -> Optional[dict]:
    """
    Télécharge et extrait le contenu d'un article.
    Cascade : HTTP → Playwright → proxies → résumé RSS.
    Retourne le dict enrichi avec 'contenu', ou None si échec.
    """
    url = article["lien"]
    try:
        html = telecharger_html(url, cache=cache)
        contenu = _extraire_texte(url, html)
        if contenu:
            _enregistrer_stat(url, succes=True)
            return {                      
                "titre":   article["titre"],
                "url":     article["lien"],
                "contenu": contenu,
                "source":  article["source"],
            }

    except ErreurPaywall:
        contenu = _contourner_paywall(article["titre"], url)
        if contenu:
            _enregistrer_stat(url, succes=True)
            return {                      
                "titre":   article["titre"],
                "url":     article["lien"],
                "contenu": contenu,
                "source":  article["source"],
            }

        contenu = _nettoyer_resume_rss(article.get("description", ""))
        if contenu:
            _enregistrer_stat(url, succes=True)
            return {                      
                "titre":   article["titre"],
                "url":     article["lien"],
                "contenu": contenu,
                "source":  article["source"],
            }

    except Exception as e:
        msg = str(e)
        if "Domaine bloqué par IP" in msg:
            contenu = _nettoyer_resume_rss(article.get("description", ""))
            if contenu:
                _enregistrer_stat(url, succes=True)
                return {                      
                    "titre":   article["titre"],
                    "url":     article["lien"],
                    "contenu": contenu,
                    "source":  article["source"],
                }

    _enregistrer_stat(url, succes=False, raison="contenu vide")
    return None


def telecharger_et_enregistrer(
    articles: list[dict],
    urls_selectionnees: set[str],
) -> list[int]:
    """
    Phase 2 — Télécharge uniquement les articles dont l'URL est dans urls_selectionnees.
    Scrape en parallèle, puis insère en batch dans la BDD avec embeddings.
    Retourne les ids insérés.
    """
    from traitements.bdd.enregistrementArticle import ajouter_articles_batch

    a_telecharger = [a for a in articles if a["lien"] in urls_selectionnees]

    cache_partage: dict = {}
    articles_ok = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futurs = {
            executor.submit(_telecharger_article, article, cache_partage): article
            for article in a_telecharger
        }
        for futur in as_completed(futurs):
            resultat = futur.result()
            if resultat:
                articles_ok.append(resultat)

    log.info(f"Téléchargement : {len(articles_ok)}/{len(a_telecharger)} articles récupérés")
    _afficher_rapport()

    return ajouter_articles_batch(articles_ok)