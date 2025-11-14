USE main_experiment;

-- Sélection principale : combine Participant, Perception (Exp1) et Crossing (Exp2)
SELECT
    p.participant_id,

    -- Distance moyenne de sécurité du participant (Exp2)
    avg_safety.avg_safety_distance,

    -- Variables démographiques
    p.height,
    p.age,

    -- Deltas de perception : (distance perçue - distance réelle)
    -- regroupés par plage de distances de disparition
    MAX(CASE WHEN pr.distance_id IN (20.0, 30.0)
             THEN (pr.perceived_distance - pr.distance_id)
             ELSE NULL
        END) AS d_l, -- low distances

    MAX(CASE WHEN pr.distance_id IN (40.0, 50.0)
             THEN (pr.perceived_distance - pr.distance_id)
             ELSE NULL
        END) AS d_m, -- medium distances

    MAX(CASE WHEN pr.distance_id IN (60.0, 70.0)
             THEN (pr.perceived_distance - pr.distance_id)
             ELSE NULL
        END) AS d_h, -- high distances

    -- Catégorie de la distance réelle (pair / odd)
    dd.category AS distance_category,

    -- Vitesse Exp1
    pr.velocity_id AS velocity_exp1,

    -- Vitesse Exp2
    c.velocity_id AS velocity_exp2

FROM Participant p

-- Jointure avec la table Crossing (Exp2)
JOIN Crossing c
    ON p.participant_id = c.participant_id

-- Jointure avec la table Perception (Exp1)
JOIN Perception pr
    ON c.participant_id = pr.participant_id
    -- Condition : même météo
    AND c.weather_id = pr.weather_id
    -- Ne garder que météo "clear"
    AND c.weather_id = 'clear'

-- Catégorie de vitesse Exp1
LEFT JOIN Velocity vc_pr
    ON pr.velocity_id = vc_pr.id

-- Catégorie de vitesse Exp2
LEFT JOIN Velocity vc_c
    ON c.velocity_id = vc_c.id

-- Catégorie des distances réelles
LEFT JOIN DistanceDisappearance dd
    ON dd.id = pr.distance_id

-- Sous-requête permettant de calculer la moyenne de sécurité du participant
LEFT JOIN (
    SELECT
        velocity_id,
        weather_id,
        participant_id,
        AVG(safety_distance) AS avg_safety_distance
    FROM Crossing
    GROUP BY velocity_id, weather_id, participant_id
) avg_safety
    ON c.velocity_id = avg_safety.velocity_id
    AND c.weather_id = avg_safety.weather_id
    AND c.participant_id = avg_safety.participant_id

WHERE
    -- On ne garde que les cas où Exp1 et Exp2 ont la même catégorie de vitesse
    vc_pr.category = vc_c.category
    -- Et uniquement la catégorie "high"
    AND vc_pr.category = 'high'

-- Agrégation par participant
GROUP BY
    p.participant_id,
    avg_safety.avg_safety_distance,
    p.height,
    p.age,
    dd.category,
    pr.velocity_id,
    c.velocity_id;
