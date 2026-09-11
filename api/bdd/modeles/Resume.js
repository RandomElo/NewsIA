import { DataTypes } from "sequelize";

export default function (bdd) {
    const Resume = bdd.define("Resumes", {
        id: {
            type: DataTypes.INTEGER,
            primaryKey: true,
            autoIncrement: true,
        },
        cluster_id: {
            type: DataTypes.INTEGER,
            allowNull: false,
        },
        cluster_id_fk: {
            type: DataTypes.INTEGER,
            allowNull: false,
            references: {
                model: "clusters",
                key: "id",
            },
            onDelete: "CASCADE",
        },
        titre: {
            type: DataTypes.TEXT,
            allowNull: false,
        },
        resume: {
            type: DataTypes.TEXT,
            allowNull: false,
        },
        date_resume: {
            type: DataTypes.DATE,
            allowNull: true,
            defaultValue: DataTypes.NOW,
        },
    }, {
        tableName: "resumes",
        timestamps: false,
    });

    return Resume;
}