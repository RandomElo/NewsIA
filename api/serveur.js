import e from "express"
import dotenv from "dotenv";
import { bdd, Article, Resume, Cluster, ClusterArticle } from "./bdd/bdd.js";
import { QueryTypes } from "sequelize";
import { Op } from "sequelize"
dotenv.config();

const { PORT_EXPRESS, BDD_URL } = process.env;
const app = e();

app.get("/resumes/:date", async (req, res) => {
    try {
        const date = req.params.date;
        const start = new Date(date + "T00:00:00.000Z");
        const end = new Date(date + "T23:59:59.999Z");

        const resumes = await Resume.findAll({
            where: {
                date_resume: {
                    [Op.gte]: start,
                    [Op.lt]: end,
                },
            },
            order: [["date_resume", "DESC"]],
            attributes: ["titre", "resume", "date_resume", "cluster_id_fk", "prix", "nb_articles_rss"],
        });

        if (!resumes.length) return res.json({ date, nbArticlesRecuperes: null, resumes: [] });

        // Même valeur sur tous les résumés d'un run ; null pour les runs antérieurs à la colonne
        const nbArticlesRecuperes = resumes.find(r => r.nb_articles_rss != null)?.nb_articles_rss ?? null;

        // Récupérer tous les clusters en une seule requête
        const clusterIds = [...new Set(resumes.map(r => r.cluster_id_fk))];

        const [clusters, clustersArticles] = await Promise.all([
            Cluster.findAll({
                where: { id: { [Op.in]: clusterIds } },
                raw: true,
            }),
            ClusterArticle.findAll({
                where: { cluster_id: { [Op.in]: clusterIds } },
                raw: true,
            }),
        ]);

        // Récupérer tous les articles en une seule requête
        const articleIds = [...new Set(clustersArticles.map(ca => ca.article_id))];
        const articles = await Article.findAll({
            where: { id: { [Op.in]: articleIds } },
            attributes: ["id", "url", "titre"],
            raw: true,
        });

        // Construire des maps pour accès O(1)
        const clusterMap = new Map(clusters.map(c => [c.id, c]));
        const articleMap = new Map(articles.map(a => [a.id, a]));
        const clusterArticlesMap = clustersArticles.reduce((acc, ca) => {
            if (!acc.has(ca.cluster_id)) acc.set(ca.cluster_id, []);
            acc.get(ca.cluster_id).push(ca.article_id);
            return acc;
        }, new Map());

        // Construire le tableau de retour sans aucune requête supplémentaire
        const tableauRetour = resumes
            .filter(resume => clusterMap.has(resume.cluster_id_fk))
            .map(resume => {
                const articleIds = clusterArticlesMap.get(resume.cluster_id_fk) ?? [];
                const sources = articleIds
                    .map(id => ({ lienArticle: articleMap.get(id)?.url, nom: articleMap.get(id).titre }))
                    .filter(Boolean);

                return { titre: resume.titre, resume: resume.resume, prix: resume.prix, sources };
            });

        res.json({ date, nbArticlesRecuperes, resumes: tableauRetour });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// Articles collectés au fil d'une journée (heure de Paris), une entrée par passage du cron.
// Lit la table collectes, qui n'est pas nettoyée le soir contrairement à articles.
app.get("/collectes/:date", async (req, res) => {
    const date = req.params.date;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return res.status(400).json({ error: "Date attendue au format AAAA-MM-JJ" });
    }
    try {
        // date_collecte est stockée en UTC (timestamp sans fuseau) : on convertit les bornes
        // de la journée de Paris en UTC pour garder l'index utilisable
        const lignes = await bdd.query(
            `SELECT to_char(date_collecte AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Paris', 'HH24:MI') AS heure,
                    nb_articles_flux, nb_nouveaux
             FROM collectes
             WHERE date_collecte >= (:date::date::timestamp AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'UTC'
               AND date_collecte < ((:date::date + 1)::timestamp AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'UTC'
             ORDER BY date_collecte`,
            { replacements: { date }, type: QueryTypes.SELECT },
        );

        let cumul = 0;
        const collectes = lignes.map(l => {
            cumul += l.nb_nouveaux;
            return { heure: l.heure, nbArticlesFlux: l.nb_articles_flux, nbNouveaux: l.nb_nouveaux, cumul };
        });

        res.json({ date, nbArticlesRecuperes: cumul, nbCollectes: collectes.length, collectes });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(PORT_EXPRESS, () => console.log(`[+] API sur http://192.168.1.31:${PORT_EXPRESS}`));