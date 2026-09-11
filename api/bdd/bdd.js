import { Sequelize } from "sequelize";
import bddArticle from "./modeles/Article.js";
import bddCluster from "./modeles/Cluster.js";
import bddClusterArticle from "./modeles/ClusterArticles.js";
import bddResume from "./modeles/Resume.js";
import dotenv from "dotenv";
dotenv.config();

const { BDD_URL } = process.env;
let bdd;
try {
    bdd = new Sequelize(process.env.BDD_URL, {
        dialect: "postgres",
        logging: false,
    });
    console.log("[+] Connexion BDD réussie");
} catch (e) {
    console.error(e)
}


// ── Instanciation des modèles ──────────────────────────────────────────────────
const Article = bddArticle(bdd);
const Cluster = bddCluster(bdd);
const ClusterArticle = bddClusterArticle(bdd);
const Resume = bddResume(bdd);

// ── Associations ───────────────────────────────────────────────────────────────

// Cluster ↔ Article  (many-to-many via clusters_articles)
Cluster.belongsToMany(Article, {
    through: ClusterArticle,
    foreignKey: "cluster_id",
    otherKey: "article_id",
    as: "articles",
});
Article.belongsToMany(Cluster, {
    through: ClusterArticle,
    foreignKey: "article_id",
    otherKey: "cluster_id",
    as: "clusters",
});

// Cluster → Resume  (one-to-many)
Cluster.hasMany(Resume, {
    foreignKey: "cluster_id_fk",
    as: "resumes",
    onDelete: "CASCADE",
});
Resume.belongsTo(Cluster, {
    foreignKey: "cluster_id_fk",
    as: "cluster",
});

export { bdd, Article, Cluster, ClusterArticle, Resume };