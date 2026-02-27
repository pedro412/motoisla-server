#!/usr/bin/env sh
set -e

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${SKIP_SUPPLIER_SEED:-0}" != "1" ]; then
  python manage.py seed_suppliers_parsers
fi

if [ "${SKIP_TAXONOMY_SEED:-0}" != "1" ]; then
  python manage.py seed_product_taxonomy
fi

if [ "${SKIP_COLLECTSTATIC:-0}" != "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
