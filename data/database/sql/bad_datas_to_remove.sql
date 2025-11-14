-- =====================================================================
-- SUPPRESSION DES DONNÉES D’UN PARTICIPANT DANS TOUTES LES TABLES
-- =====================================================================

-- Ce script sert à retirer complètement un participant de la base.
-- Il doit être utilisé uniquement lorsqu’un participant doit être
-- exclu (ex : crash VR, données corrompues, abandon en cours d'expériment).

-- Remplacer 'XXX_29' par l'identifiant du participant concerné.

-- ---------------------------------------------------------------------
-- 1. Supprimer les entrées de l'expérience 1 (Perception)
-- ---------------------------------------------------------------------
DELETE FROM Perception
WHERE participant_id = 'XXX_29';

-- ---------------------------------------------------------------------
-- 2. Supprimer les entrées de l'expérience 2 (Crossing)
-- ---------------------------------------------------------------------
DELETE FROM Crossing
WHERE participant_id = 'XXX_29';

-- ---------------------------------------------------------------------
-- 3. Supprimer l’entrée du participant lui-même
-- ---------------------------------------------------------------------
DELETE FROM Participant
WHERE participant_id = 'XXX_29';


-- =====================================================================
-- SUPPRESSION D’ENTRÉES INDIVIDUELLES (AU CAS PAR CAS)
-- =====================================================================

-- Exemple : vérifier une ligne Perception précise
SELECT * FROM Perception
WHERE perception_id = '28';

-- Supprimer une ligne précise (par exemple si corrompue)
DELETE FROM Perception
WHERE perception_id = '28';
