-- ===========================================================================
-- Création de la base de données
-- ===========================================================================

-- Supprime la base si elle existe déjà
DROP DATABASE IF EXISTS main_experiment;

-- Crée une nouvelle base de données
CREATE DATABASE main_experiment;

-- Sélectionne la base
USE main_experiment;

-- ===========================================================================
-- Table Participant
-- Contient les informations générales et anonymisées des participants
-- ===========================================================================
CREATE TABLE Participant (
    participant_id VARCHAR(6) PRIMARY KEY,    -- Identifiant unique du participant
    age INT,                                  -- Age en années
    sex VARCHAR(6),                            -- Sexe (ex: "male", "female")
    height INT,                                -- Taille en centimètres
    driver_license BOOLEAN,                    -- Possession du permis de conduire (0/1)
    scale INT                                  -- Valeur liée à la calibration du casque VR si utilisée
);

-- ===========================================================================
-- Table Weather
-- Liste des conditions météo utilisées dans les expériences
-- ===========================================================================
CREATE TABLE Weather (
    id VARCHAR(6) PRIMARY KEY                 -- Nom court de la météo (ex: "night", "clear", "rain")
);

-- ===========================================================================
-- Table Position
-- Positions fixes du piéton dans l'expérience 2
-- ===========================================================================
CREATE TABLE Position (
    id INT PRIMARY KEY                        -- 0, 1 ou 2 selon la position dans la scène
);

-- ===========================================================================
-- Table Velocity
-- Vitesse du véhicule et sa catégorie associée
-- ===========================================================================
CREATE TABLE Velocity (
    id FLOAT PRIMARY KEY,                     -- Vitesse en km/h
    category ENUM('low', 'medium', 'high') NOT NULL  -- Catégorisation qualitative
);

-- ===========================================================================
-- Table DistanceDisappearance
-- Distances de disparition du véhicule dans l'expérience 1
-- ===========================================================================
CREATE TABLE DistanceDisappearance (
    id FLOAT PRIMARY KEY,                     -- Valeur numérique de la distance en mètres
    category ENUM('pair', 'odd') NOT NULL     -- Classification pair / impair
);

-- ===========================================================================
-- Table Perception (Expérience 1)
-- Stocke les données du moment où le participant effectue le "snap"
-- ===========================================================================
CREATE TABLE Perception (
    perception_id INT AUTO_INCREMENT PRIMARY KEY,   -- Identifiant interne
    participant_id VARCHAR(6),                      -- Référence au participant
    perceived_distance FLOAT,                       -- Distance estimée ou variable équivalente
    weather_id VARCHAR(6),                          -- Condition météo
    velocity_id FLOAT,                              -- Vitesse du véhicule
    distance_id FLOAT,                              -- Distance de disparition du véhicule

    -- Contraintes d'intégrité
    FOREIGN KEY (participant_id) REFERENCES Participant(participant_id),
    FOREIGN KEY (weather_id) REFERENCES Weather(id),
    FOREIGN KEY (velocity_id) REFERENCES Velocity(id),
    FOREIGN KEY (distance_id) REFERENCES DistanceDisappearance(id)
);

-- ===========================================================================
-- Table Crossing (Expérience 2)
-- Stocke les données continues de décision de traversée
-- ===========================================================================
CREATE TABLE Crossing (
    crossing_id INT AUTO_INCREMENT PRIMARY KEY,  -- Identifiant interne
    participant_id VARCHAR(6),                    -- Identifiant du participant
    weather_id VARCHAR(6),                        -- Condition météo
    position_id INT,                              -- Position du piéton
    velocity_id FLOAT,                            -- Vitesse du véhicule
    
    distance_car_ped JSON,                        -- Distances véhicule-piéton synchronisées (format JSON)
    crossing_value JSON,                          -- Valeur 0/1 du crossing en continu (format JSON)
    safety_distance FLOAT,                        -- Distance au moment où la décision passe de 1 à 0

    -- Contraintes d'intégrité
    FOREIGN KEY (participant_id) REFERENCES Participant(participant_id),
    FOREIGN KEY (weather_id) REFERENCES Weather(id),
    FOREIGN KEY (position_id) REFERENCES Position (id),
    FOREIGN KEY (velocity_id) REFERENCES Velocity(id)
);

-- ===========================================================================
-- Insertion des valeurs fixes dans Weather
-- ===========================================================================
INSERT INTO Weather (id) 
VALUES ('night'), 
       ('clear'), 
       ('rain');

-- ===========================================================================
-- Insertion des valeurs fixes dans Position
-- ===========================================================================
INSERT INTO Position (id) 
VALUES (0),
       (1),
       (2);

-- ===========================================================================
-- Insertion des valeurs fixes dans Velocity
-- ===========================================================================
INSERT INTO Velocity (id, category)
VALUES (20.0, 'low'),
       (30.0, 'low'),
       (40.0, 'medium'),
       (50.0, 'medium'),
       (60.0, 'high'),
       (70.0, 'high');

-- ===========================================================================
-- Insertion des valeurs fixes dans DistanceDisappearance
-- ===========================================================================
INSERT INTO DistanceDisappearance (id, category)
VALUES (20.0, 'pair'),
       (30.0, 'odd'),
       (40.0, 'pair'),
       (50.0, 'odd'),
       (60.0, 'pair'),
       (70.0, 'odd');
