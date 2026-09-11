import e, { raw } from "express"
import dotenv from "dotenv";
import { Article, Resume, Cluster, ClusterArticle } from "./bdd/bdd.js";
import path from "path"
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
            attributes: ["titre", "resume", "date_resume", "cluster_id_fk"],
        });

        if (!resumes.length) return res.json([]);

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

                return { titre: resume.titre, resume: resume.resume, sources };
            });

        res.json(tableauRetour);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(PORT_EXPRESS, () => console.log(`[+] API sur http://192.168.1.31:${PORT_EXPRESS}`));