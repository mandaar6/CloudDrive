import json

filepath = r'c:\D\UWB\CloudDrive\clouddrive\dashboard\dashboards\clouddrive.json'
with open(filepath, 'r', encoding='utf-8') as f:
    dash = json.load(f)

for p in dash['panels']:
    if p.get('type') == 'timeseries':
        custom = p.get('fieldConfig', {}).get('defaults', {}).get('custom', {})
        
        # Change to Stacked Bars instead of Area/Lines
        custom['drawStyle'] = "bars"
        custom['fillOpacity'] = 80
        custom['lineWidth'] = 0
        custom['stacking'] = {"group": "A", "mode": "normal"}
        
        # Clean up line-specific properties
        if 'showPoints' in custom:
            del custom['showPoints']
        if 'spanNulls' in custom:
            del custom['spanNulls']

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(dash, f, indent=2)

print('Converted timeseries panels to Stacked Bar charts!')
