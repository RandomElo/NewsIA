import { DataTypes } from "sequelize";

export default function (bdd) {
    const Cluster = bdd.define("Clusters", {
        id: {
            type: DataTypes.INTEGER,
            primaryKey: true,
            autoIncrement: true,
        },
        topic_id: {
            type: DataTypes.INTEGER,
            allowNull: false,
        },
        titre: {
            type: DataTypes.TEXT,
            allowNull: false,
        },
        date_run: {
            type: DataTypes.DATE,
            allowNull: false,
        },
    }, {
        tableName: "clusters",
        timestamps: false,
    });

    return Cluster;
}