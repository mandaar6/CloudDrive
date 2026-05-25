import json

filepath = r'c:\D\UWB\CloudDrive\clouddrive\dashboard\dashboards\clouddrive.json'
with open(filepath, 'r', encoding='utf-8') as f:
    dash = json.load(f)

for p in dash['panels']:
    if p.get('type') == 'logs':
        for target in p.get('targets', []):
            if 'maxDataPoints' in target:
                del target['maxDataPoints']
            # Make sure container match is regex
            if 'clouddrive-db-1' in target['expr']:
                target['expr'] = target['expr'].replace('container="clouddrive-db-1"', 'container=~".*db.*"')

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(dash, f, indent=2)

print('Logs panels sanitized!')
