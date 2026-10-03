# Serveur de fichiers interne

Service HTTP en Python (FastAPI + Uvicorn) permettant à des utilisateurs
authentifiés de déposer, lister, télécharger et supprimer des fichiers, avec
notifications en temps réel par WebSocket.

## Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements.txt

export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

Ouvrir http://127.0.0.1:5000 pour la connexion, puis
http://127.0.0.1:5000/app pour l'application. La documentation interactive
des routes est disponible sur http://127.0.0.1:5000/docs.

Un administrateur peut créer des comptes depuis la section
**Administration** de l'interface, après connexion avec un compte ayant le
rôle `admin`. Le nom d'utilisateur accepte les lettres, chiffres, `.`, `_`
et `-`, et le mot de passe doit contenir au moins 8 caractères.

Les mots de passe ne sont jamais enregistrés en clair : ils sont hachés avec
`scrypt`, un sel unique et des paramètres de coût mémoire. Le champ
`password_hash` de `data/users.json` peut donc être conservé, mais ne doit
jamais être copié ou affiché dans l'interface. Lorsqu'un ancien hash valide
utilise des paramètres différents, il est automatiquement recalculé après une
connexion réussie.

Comptes de démonstration fournis dans `data/users.json` :

| Utilisateur | Mot de passe  | Rôle  |
|-------------|---------------|-------|
| alice       | `Alice#2026!` | user  |
| bob         | `Bob#2026!`   | user  |
| admin       | `Admin#2026!` | admin |

**Changer ces mots de passe avant tout déploiement public.**

```bash
python -m scripts.create_user alice --role user     # demande le mot de passe, le hache, l'enregistre
```

## Variables d'environnement

| Variable             | Rôle                                                   | Défaut        |
|----------------------|--------------------------------------------------------|---------------|
| `JWT_SECRET`         | Clé de signature des jetons (**obligatoire en prod**)  | aléatoire     |
| `JWT_EXPIRE_MINUTES` | Durée de vie d'un jeton                                | 30            |
| `MAX_UPLOAD_MB`      | Taille maximale d'un fichier                           | 10            |
| `DATA_DIR`           | Dossier de `users.json` et `files_meta.json`           | `./data`      |
| `STORAGE_DIR`        | Dossier des fichiers déposés                           | `./storage`   |

## Routes

| Méthode | Route            | Auth | Description                                             | Succès | Erreurs            |
|---------|------------------|------|---------------------------------------------------------|--------|--------------------|
| POST    | `/login`         | non  | Vérifie les identifiants, retourne un jeton             | 200    | 401, 422, 429      |
| GET     | `/files`         | oui  | Liste les fichiers (nom, taille, date, propriétaire)    | 200    | 401                |
| POST    | `/files`         | oui  | Téléverse un fichier (`multipart/form-data`, champ `file`) | 201 | 400, 401, 409, 413 |
| GET     | `/files/{nom}`   | oui  | Télécharge un fichier                                   | 200    | 400, 401, 404      |
| DELETE  | `/files/{nom}`   | oui  | Supprime (propriétaire ou administrateur)               | 204    | 400, 401, 403, 404 |
| WS      | `/ws?token=...`  | oui  | Notifications `uploaded` / `deleted`                    | 101    | 403 (jeton invalide) |

Les routes protégées attendent l'en-tête `Authorization: Bearer <jeton>`.

## Tests

```bash
python -m unittest tests.test_services -v     # services : sans dépendance externe
pip install -r requirements-dev.txt
python -m unittest tests.test_api -v          # API complète, droits, WebSocket
```

## Déploiement

- Commande de démarrage : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Définir `JWT_SECRET` dans les variables d'environnement de la plateforme.
- Utiliser **un seul worker** : la liste des clients WebSocket est en mémoire.
- Monter un disque persistant et pointer `DATA_DIR` / `STORAGE_DIR` dessus, sinon les
  fichiers disparaissent à chaque redéploiement sur la plupart des hébergeurs gratuits.
- Servir en HTTPS : sinon le jeton circule en clair. Derrière un proxy, ajouter
  `--proxy-headers` pour que la limitation de tentatives voie la vraie adresse IP.

### Déploiement avec Docker sur un VPN

Construire l'image depuis la racine du projet :

```bash
docker build -t filehub:latest .
```

Lancer le conteneur avec des volumes persistants et une clé JWT stable :

```bash
docker volume create filehub-data
docker volume create filehub-storage
docker run -d \
  --name filehub \
  --restart unless-stopped \
  -p 5000:5000 \
  -e JWT_SECRET="remplacer-par-une-cle-secrete-longue" \
  -v filehub-data:/var/lib/filehub/data \
  -v filehub-storage:/var/lib/filehub/storage \
  filehub:latest
```

Depuis le VPN, l'application sera accessible sur
`http://ADRESSE_IP_DU_SERVEUR:5000`. Le port `5000/TCP` doit être autorisé
dans le pare-feu du serveur et dans le réseau VPN. Pour conserver les
notifications WebSocket, le proxy éventuel doit autoriser l'upgrade
WebSocket sur `/ws`.

Le conteneur utilise un seul processus Uvicorn : le gestionnaire des clients
WebSocket est conservé en mémoire. Les volumes `filehub-data` et
`filehub-storage` conservent respectivement les utilisateurs/métadonnées et
les fichiers déposés lors des redémarrages.

Au premier démarrage, le conteneur copie automatiquement le fichier
`users.json` initial dans le volume de données s'il n'existe pas encore.

## Structure

```
app/
  main.py            assemblage de l'application, en-têtes de sécurité
  config.py          chemins, durée des jetons, limites (variables d'environnement)
  models.py          schémas Pydantic des requêtes, réponses et événements
  security.py        hachage scrypt, création et lecture des JWT
  dependencies.py    utilisateur courant, règle de suppression
  routers/           auth.py, files.py, ws.py  (HTTP uniquement)
  services/          users.py, storage.py, notifier.py, login_guard.py  (logique métier)
static/              index.html, app.js, style.css
scripts/             create_user.py
tests/               test_services.py, test_api.py
```
