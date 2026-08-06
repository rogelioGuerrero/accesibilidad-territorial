import json, sys
sys.path.insert(0, '.')

d = json.load(open('tests/fixtures/benchmark_results.json'))

print("=== ORS/VROOM ===")
for r in d['ors_vroom']['routes']:
    steps_info = []
    for s in r['steps']:
        t = s['type']
        if t == 'job':
            steps_info.append(f"job#{s.get('id','?')}")
        elif t == 'break':
            steps_info.append(f"break#{s.get('id','?')}")
        else:
            steps_info.append(t)
    print(f"  Veh {r['vehicle']}: dur={r['duration']} cost={r['cost']} steps={steps_info}")

print()
print("=== OR-Tools ===")
for r in d['ortools']['routes']:
    steps_info = [s['type'] + (f"({s['location_id']})" if s['type'] == 'delivery' else "") for s in r['steps']]
    print(f"  {r['vehicle_id']}: dist={r['total_distance']} travel={r['travel_time']} total_dur={r['total_duration']} stops={steps_info}")
