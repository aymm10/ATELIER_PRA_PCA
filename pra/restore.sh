#!/bin/bash
# =============================================================================
# restore.sh — Restauration vers un point de restauration choisi
# Usage : ./pra/restore.sh [nom_du_fichier_backup]
# Exemple : ./pra/restore.sh app-1772096403.db
# =============================================================================

set -e

RESTORE_FILE=$1
NAMESPACE="pra"
JOB_MANIFEST="pra/51-job-restore-point.yaml"

# ---------- 1. Si aucun fichier fourni, lister les backups disponibles ----------
if [ -z "$RESTORE_FILE" ]; then
  echo ""
  echo "Usage : ./pra/restore.sh <nom_du_fichier_backup>"
  echo ""
  echo "Backups disponibles dans le PVC pra-backup :"
  echo "---------------------------------------------"
  kubectl -n $NAMESPACE run list-backups \
    --rm -it \
    --image=alpine \
    --restart=Never \
    --overrides='{
      "spec": {
        "containers": [{
          "name": "list",
          "image": "alpine",
          "command": ["sh", "-c", "ls -lht /backup/*.db"],
          "stdin": true,
          "tty": true,
          "volumeMounts": [{
            "name": "backup",
            "mountPath": "/backup"
          }]
        }],
        "volumes": [{
          "name": "backup",
          "persistentVolumeClaim": {
            "claimName": "pra-backup"
          }
        }]
      }
    }' 2>/dev/null
  echo ""
  echo "Relancez le script avec le fichier souhaité."
  echo "Exemple : ./pra/restore.sh app-1772096403.db"
  exit 0
fi

echo ""
echo "========================================================"
echo "  PHASE 1 — Mise en sécurité avant restauration"
echo "========================================================"

# Arrêt de l'application
echo "⏸  Scale down du Deployment Flask..."
kubectl -n $NAMESPACE scale deployment flask --replicas=0

# Suspension du CronJob de backup
echo "⏸  Suspension du CronJob sqlite-backup..."
kubectl -n $NAMESPACE patch cronjob sqlite-backup -p '{"spec":{"suspend":true}}'

# Suppression des jobs en cours
echo "🗑  Suppression des anciens jobs..."
kubectl -n $NAMESPACE delete job --all --ignore-not-found > /dev/null

echo ""
echo "========================================================"
echo "  PHASE 2 — Restauration vers : $RESTORE_FILE"
echo "========================================================"

# Injection du nom du fichier dans le manifest et lancement du Job
echo " Lancement du Job de restauration..."
kubectl -n $NAMESPACE delete job sqlite-restore-point --ignore-not-found > /dev/null
sed "s/app-XXXXXXXXXX.db/$RESTORE_FILE/" $JOB_MANIFEST | kubectl apply -f -

# Attente de la fin du Job
echo " Attente de la fin du Job..."
kubectl -n $NAMESPACE wait --for=condition=complete job/sqlite-restore-point --timeout=60s

# Affichage des logs du Job
echo ""
echo " Logs du Job de restauration :"
kubectl -n $NAMESPACE logs job/sqlite-restore-point

echo ""
echo "========================================================"
echo "  PHASE 3 — Redémarrage de l'application"
echo "========================================================"

# Redémarrage du Deployment
echo "  Scale up du Deployment Flask..."
kubectl -n $NAMESPACE scale deployment flask --replicas=1

# Réactivation du CronJob de backup
echo "  Réactivation du CronJob sqlite-backup..."
kubectl -n $NAMESPACE patch cronjob sqlite-backup -p '{"spec":{"suspend":false}}'

# Attente que le pod soit prêt
echo " Attente que le pod Flask soit Ready..."
kubectl -n $NAMESPACE wait --for=condition=ready pod -l app=flask --timeout=60s

# Forward du port
echo " Forward du port 8080..."
pkill -f "port-forward svc/flask" 2>/dev/null || true
kubectl -n $NAMESPACE port-forward svc/flask 8080:80 >/tmp/web.log 2>&1 &

echo ""
echo " Restauration terminée avec succès !"
echo "   Point de restauration utilisé : $RESTORE_FILE"
echo "   Vérifiez vos données sur /consultation et /count"
echo "========================================================"