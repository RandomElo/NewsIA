import { DataTypes } from "sequelize";

export default function (bdd) {
    const ClusterArticle = bdd.define("ClustersArticles", {
        cluster_id: {
            type: DataTypes.INTEGER,
            allowNull: false,
            references: {
                model: "clusters",
                key: "id",
            },
            onDelete: "CASCADE",
        },
        article_id: {
            type: DataTypes.INTEGER,
            allowNull: false,
            references: {
                model: "articles",
                key: "id",
            },
            onDelete: "CASCADE",
        },
    }, {
        tableName: "cluster_articles",
        timestamps: false,
    });

    return ClusterArticle;
}