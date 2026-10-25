# Local demo with Docker. `make demo` builds everything, creates database "demo" and loads synthetic data.
DB ?= demo

up:
	docker compose up -d --build

demo: up
	docker compose exec odoo odoo -d $(DB) -i smart_reconcile --without-demo=all --stop-after-init
	docker compose exec -T -e DEMO_JSON=/mnt/data/demo.json odoo odoo shell -d $(DB) --no-http < scripts/load_demo_data.py
	@echo "Open http://localhost:8069 (database $(DB), user admin / admin)"

e2e:
	docker compose exec -T -e DEMO_JSON=/mnt/data/demo.json odoo odoo shell -d $(DB) --no-http < scripts/e2e_check.py

retrain:
	docker compose exec ml python -m smart_reconcile_ml.train --data data/generated/v1 --out models/latest \
		--feedback /app/feedback
	docker compose restart ml

reset-demo:  # fresh demo database with unreconciled bank lines (no end-to-end check)
	docker compose exec -T -e PGPASSWORD=odoo odoo dropdb --force --if-exists -h db -U odoo $(DB)
	docker compose exec odoo odoo -d $(DB) -i smart_reconcile --without-demo=all --stop-after-init
	docker compose exec -T -e DEMO_JSON=/mnt/data/demo.json odoo odoo shell -d $(DB) --no-http < scripts/load_demo_data.py
	docker compose restart odoo

screenshots:  # needs: pip install playwright pillow (uses the installed Chrome)
	python scripts/screenshots.py --url http://localhost:8069 --db $(DB)

down:
	docker compose down

.PHONY: up demo e2e retrain reset-demo screenshots down
