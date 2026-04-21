```
I have this outdated rpi file which I wrote previously, I want the future rpi files in the execution style this one is in

now heres the plan, I need to update all the files


one would be rpi file, and another would be a server file

rpi file will have the detections side.

heres what it does
when it gets a signal from a lane sensor it will trigger the camera, and get its image. It will make sure it wasn't a false positive, it will then send information regarding that detection over to the server.

the server then parses through the informatio provided and updates all the stats and stuff and logs it.

details:

rpi idle- when idle the the rpi script just waits for a lane signal trigger.

lane signal- for now we have pivotted from pir sensors in the road to button type pressure sensors (they are just buttons for now) which (were supposed to be connected to the rpi board with the esp boards, but we haven't received them yet, so for now we'll go with something simple for now) will be connected to one the pins on the rpi board, 1 pin for each lane, and a high signal from them means a car is detected.

note for each lane's sensor we are storing the following information:
(lane_id, first/second sensor in lane (0 for first, 1 for second), which camera to trigger, facing direction (ie assuming each lane is unidirectional, which nameplate side of car will we see when camera is triggered, 0 for car's back, 1 for car's front))

signalling camera-
once the signal is received from the first button the lane, the camera will be triggered using the connected phone camera (you need to tell me steps to connect it to rpi)
once it gets the image, it will check if it for false positive (no vehicle and stuff just like how we did it for vigil capture earlier)
one thing to note, just keep a parameter at the top of the file NO_VEHICLE_FILTER (true/false), which does what the flag was doing. 
once we know it wasn't a false positive, we calculate the speed of the vehicle using the time differential between the 2 button triggers of the same lane. we then send info to server.

sending the server information-
so each lane has with it an associated (entry_area, exit_area) that means if the car was detected in this lane (assuming for now the lane only allows cars in one direction), the tuple will tell which area the car is now entering and which it just exited.
the rpi script will send the following info (entry_area, exit_area, speed, nameplate, nameplate's per character confidence, the captured image)
the entry or exit area can also be OUT, meaning that area is outside the network


server side details:
we maintain a nameplate_database (a table), which for now contains the following columuns (nameplate, regsitered (bool), parked (bool), last_area, owner, owner_phone_number, violations(int))

a notification table (nameplate, area, time, speed, owner, owner_phonenumber, image(maybe as as a link?)).
a traffic stats table (area, active_vehicles, avg_speed (you can also maintain a number of observations for updating this column)).

traffic log table (area, nameplate, status column (entry, exit, parked)).

an undirected graph with the 'areas' as the nodes (not sure what a good representation for this is, but we only need adjacency information).


idle- when idle, the server just waits for an information packet from an rpi. in between if a parked_timer for a nameplate may go off which we would need to service it (talked later).

recived information-
upon recieving the packet it first does a nameplate search as follows; it checks the per character confidence, if a character confidence is less than 40% (keep a variable at the top of the file CHAR_CONFIDENCE_THRESHOLD for this) it treats that character position in the nameplate as a 'wild' character. now with this new nameplate, it searches through its database of vehicles to shortlist a subset of them (if this is empty we will handle the original nameplate as a new namplate). then from this shortlisted nameplates, we will check if their last_area was adjacent to exit_area or not (using the graph, btw this is the only place we use the 'graph' so no need to add too many features for it, just make this part easy), if not we disregard that this nameplate entry in our search. in the end if we are still left with multiple entries, we just take one at random. If instead no entry is left, we take that as a new nameplate

if the shortlist cameup empty or no valid matches were found, we add the originally detected nameplate (before replacing with the wild characters) to nameplate_database as a new nameplate, we also make its 'unregistered' entry as true.

once the nameplate is finalized, we reset the parked_timer on that nameplate to 5 minutes.
we then updated the following stats:
traffic log gets
number of active vehicles in exit_area is -1, (traffic stats)
number of active vehicles in entry_area is +1. (traffic stats)
update the avg speed of this entry_area with the new speed
(note, we do not track traffic stats for the OUT area)
traffic log gets 2 new entries, one for exit area and one for entry area, for this nameplate (it still gets an entry even if the area is OUT)

if the speed was above threshold, we update the notification log table and we add a +1 to the speed_violation entry for this vehicle in the nameplate database

update the nameplate database regarding this nameplate- last_area is now the entry_area (in case this is OUT, we write the entry as OUT itself)

there are some other stats but for now we shall maintain these few basic ones

if a parked_timer goes off:
we mark the entry of that nameplate in the working_database, 'parked' as true
and the last_area's traffic stat as -1
and the traffic log gets a new entry for this nameplate, and status parked
```


This is a big one — three files making up the full VIGIL system. Let me plan the architecture first, then write everything.

**Architecture:**
- `cap_inf.py` — shared camera + ALPR module (imported by RPi script)
- `rpi_detector.py` — RPi entry point: lane sensors → camera → ALPR → send to server
- `vigil_server.py` — Flask server: receives detections, manages database, timers, stats

Let me write all three.Here's the full system — three files:

---

**`cap_inf.py`** — The shared module. Both the RPi script and your old `vigil_capture.py` import from this. Contains `init_alpr`, `init_vehicle_detector`, `grab_snapshot`, `run_alpr_on_frame`, etc. Nothing changed functionally, just extracted into a clean importable module.

**`rpi_detector.py`** — The RPi entry point, written in the same style as your `pir_trigger.py`. Key design:

- **Lane config** at the top as a list of dicts — each lane defines `pin_first`, `pin_second`, `camera_url`, `facing`, `entry_area`, `exit_area`. Adding a lane is just adding a dict.
- **Flow:** polls all lanes → first sensor triggers → camera snapshot + ALPR with vehicle filter → waits for second sensor → calculates speed → POSTs packet to server via `requests`.
- **`NO_VEHICLE_FILTER`** at the top of the file, exactly as you asked.
- Handles reverse traffic (sensor2 before sensor1) and timeouts.
- Phone camera setup instructions are in the docstring at the top.

**`vigil_server.py`** — Flask server with SQLite. This is the meatiest file:

- **4 tables:** `nameplates`, `notifications`, `traffic_stats`, `traffic_log` — all auto-created on startup.
- **Nameplate matching:** replaces characters below `CHAR_CONFIDENCE_THRESHOLD` (40%) with SQL `_` wildcards, queries the database, filters candidates by adjacency (candidate's `last_area` must neighbor `exit_area`), picks one at random if multiple match, falls back to inserting as new/unregistered.
- **Area adjacency:** simple Python dict at the top (`AREA_ADJACENCY`). Only used for the adjacency check during matching.
- **Parked timers:** uses `threading.Timer`. Every detection resets that plate's timer to 5 minutes. When it fires: marks `parked=True`, decrements the area's `active_vehicles`, adds a "parked" entry to `traffic_log`. The timer dict is thread-safe.
- **Speed violations:** if speed > `SPEED_LIMIT_KMPH`, increments `violations` count and adds a notification entry.
- **Debug endpoints:** `/api/stats`, `/api/nameplates`, `/api/notifications`, `/api/log`, `/api/timers` — all GET, return JSON. Useful for testing.
- `--seed` flag to pre-populate some test vehicles.

**Dependencies to install:**
- RPi: `pip install 'fast-alpr[onnx]' ultralytics opencv-python requests RPi.GPIO`
- Server: `pip install flask`