# Speed

Speed est un jeu de course de GPS, conçu pour la Fête de la science. L’objectif est de trouver un trajet rapide à travers une ville, puis de comparer son parcours à celui d’un robot pour découvrir les algorithmes de recherche de chemin.

Avec Python 3.11 ou plus récent, depuis la racine du projet, l’installation des dépendances avec pip et le lancement du jeu se font de la manière suivante :

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Le navigateur s’ouvre sur [http://localhost:8000](http://localhost:8000). Le terminal doit rester ouvert pendant le jeu ; `Ctrl+C` arrête le serveur.

Pour jouer, il suffit de choisir un niveau, de préférence **Facile** pour commencer, puis de cliquer sur **JOUER**. Le trajet se construit en cliquant sur les carrefours voisins, du garage jusqu’au drapeau : les rues vertes sont rapides et les voitures orange signalent des ralentissements. **Annuler** permet de retirer la dernière étape. Une fois le trajet terminé, **Valider le trajet** lance la démonstration de recherche du robot, puis la course. Après l’arrivée, **Pourquoi ce chemin ?** permet d’observer le trajet optimal et **Nouvelle course** de recommencer.

## Aperçu

[![Aperçu du jeu Speed](./docs/game.png)](./docs/game.png)