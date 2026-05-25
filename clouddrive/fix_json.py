import json
import os

filepath = r'c:\D\UWB\CloudDrive\clouddrive\dashboard\dashboards\clouddrive.json'
with open(filepath, 'r', encoding='utf-8') as f:
    dash = json.load(f)

for panel in dash.get('panels', []):
    # Remove hardcoded intervals to allow auto-scaling
    if 'options' in panel and 'interval' in panel['options']:
        del panel['options']['interval']
    if 'interval' in panel:
        del panel['interval']
    
    is_stat = panel.get('type') in ['stat', 'gauge']
    
    for target in panel.get('targets', []):
        if is_stat:
            # Stat panels just want the total over the selected time range.
            target['expr'] = target['expr'].replace('[$__interval]', '[$__range]')
            target['queryType'] = 'range' # Use range with maxDataPoints = 1
            target['maxDataPoints'] = 1 
            # Or we can just use instant, but range with 1 datapoint works perfectly in Grafana stats
        else:
            # Timeseries panels use interval
            target['expr'] = target['expr'].replace('[$__range]', '[$__interval]')
            target['maxDataPoints'] = 20 # A reasonable number of points for a graph

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(dash, f, indent=2)

print("Dashboard JSON optimized successfully!")
