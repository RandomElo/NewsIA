import { DataTypes } from "sequelize";

export default function (bdd) {
    const Article = bdd.define("Articles", {
        id: {
            type: DataTypes.INTEGER,
            primaryKey: true,
            autoIncrement: true,
        },
        titre: {
            type: DataTypes.TEXT,
            allowNull: false,
        },
        url: {
            type: DataTypes.TEXT,
            allowNull: false,
            unique: true,
        },
        contenu: {
            type: DataTypes.TEXT,
            allowNull: true,
        },
        source: {
            type: DataTypes.TEXT,
            allowNull: true,
        },
        embedding: {
            type: DataTypes.STRING,
            allowNull: true,
        },
        date_ajout: {
            type: DataTypes.DATE,
            allowNull: true,
        },
    }, {
        tableName: "articles",
        timestamps: false,
    });

    return Article;
}