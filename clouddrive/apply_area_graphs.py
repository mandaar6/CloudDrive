import json

filepath = r'c:\D\UWB\CloudDrive\clouddrive\dashboard\dashboards\clouddrive.json'
with open(filepath, 'r', encoding='utf-8') as f:
    dash = json.load(f)

for p in dash['panels']:
    if p.get('type') == 'timeseries':
        custom = p.get('fieldConfig', {}).get('defaults', {}).get('custom', {})
        
        # Revert to Area Graphs with Stacking (Option 2)
        custom['drawStyle'] = "line"
        custom['fillOpacity'] = 60
        custom['lineWidth'] = 2
        custom['lineInterpolation'] = "linear"
        custom['showPoints'] = "never"
        custom['spanNulls'] = True
        custom['gradientMode'] = "opacity"
        custom['stacking'] = {"group": "A", "mode": "normal"}

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(dash, f, indent=2)

print('Reverted all timeseries panels to Area Graphs with Stacking.')
