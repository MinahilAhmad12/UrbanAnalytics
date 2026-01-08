# import requests
# import pandas as pd

# url = "https://api.openaq.org/v3/measurements/"

# headers = {
#     "accept": "application/json",
#     "X-API-Key": "850e0859c99c4c0ca69d471c483500a2ab0c9b59d3ee12cb46175487420ecb8d"
# }

# params = {
#     "city": "Lahore",
#     "parameter": "pm25",
#     "date_from": "2023-01-01",
#     "date_to": "2023-12-31",
#     "limit": 1000
# }

# resp = requests.get(url, headers=headers, params=params)
# print(resp.status_code)
# print(resp.json())
# exit()
# data = resp.json()["results"]

# rows = []
# for r in data:
#     if r.get("coordinates"):
#         rows.append({
#             "lat": r["coordinates"]["latitude"],
#             "lon": r["coordinates"]["longitude"],
#             "date": r["date"]["utc"],
#             "pm25": r["value"]
#         })

# df = pd.DataFrame(rows)
# df.to_csv("lahore_pm25_2023.csv", index=False)

import requests

url = "https://api.openaq.org/v3/locations/"

headers = {
    "accept": "application/json",
    "X-API-Key": "850e0859c99c4c0ca69d471c483500a2ab0c9b59d3ee12cb46175487420ecb8d"
}

params = {
    "country": "PK",
    "limit": 5
}

resp = requests.get(url, headers=headers, params=params)

print(resp.status_code)
print(resp.json())


