import re

with open('iot/simulation/demo_visual.html', encoding='utf-8') as f:
    html = f.read()

with open('iot/simulation/app.js', encoding='utf-8') as f:
    app_js = f.read()

with open('iot/simulation/scene3d.js', encoding='utf-8') as f:
    scene_js = f.read()

ids_in_app = re.findall(r'\$\("([^"]+)"\)', app_js) + re.findall(r'getElementById\("([^"]+)"\)', app_js)
ids_in_scene = re.findall(r'getElementById\("([^"]+)"\)', scene_js)

html_ids = set(re.findall(r'id="([^"]+)"', html))

missing = []
for i in set(ids_in_app):
    if i not in html_ids:
        missing.append(('app.js', i))

for i in set(ids_in_scene):
    if i not in html_ids:
        missing.append(('scene3d.js', i))

print("Total HTML IDs:", len(html_ids))
print("Missing IDs:", missing)

# Check all fixture images exist
fixtures = re.findall(r'fixtures/[a-zA-Z0-9_\-\.]+', app_js) + re.findall(r'fixtures/[a-zA-Z0-9_\-\.]+', html)
import os
print("\n--- Checking Fixtures ---")
for fix in set(fixtures):
    full_path = os.path.join('iot', 'simulation', fix.replace('/', os.sep))
    exists = os.path.exists(full_path)
    size = os.path.getsize(full_path) if exists else 0
    print(f"Fixture: {fix} -> Exists: {exists}, Size: {size} bytes")
