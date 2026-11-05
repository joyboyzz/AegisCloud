.PHONY: install bootstrap run test clean
install:    ; pip install -r requirements.txt
bootstrap:  ; python scripts/bootstrap.py
run:        ; python run.py
test:       ; python -m pytest tests/ -q
clean:      ; find . -type d -name '__pycache__' -prune -exec rm -rf {} +; rm -rf .pytest_cache
