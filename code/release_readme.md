# HAI-CPPS v2.2 dataset

HAI-CPPS v2.2 records every topology for 25,000 one-second simulation
intervals. Each exported table contains 25,001 canonical rows because time 0
and time 25,000 are both included.

Each released anomaly has two seed-matched test recordings after an initial
2,500-interval healthy period:

- ordinal `001`, directory suffix `_persistent`: active from time 2,500
  through the recording end;
- ordinal `002`, directory suffix `_temporal`: active for exactly 5,000
  intervals on `[2500, 7500)`.

Healthy recordings keep the v2.1 split of ten training, three validation, two
calibration, and one test recording per topology. Both anomaly variants are
paired with the seed-42 healthy test control. Fault-window flags and all oracle
variables are offline metadata and are excluded from permitted diagnosis
inputs.

The release is generated in topology shards. Each shard contains its campaign
manifest, frozen generation source, licence, and recordings under a second
topology directory. `campaign.json`, `sim_setup.json`, `fault_events.json`,
`technical_timing.json`, `provenance.json`, and `validation.json` provide the
exact window and source identity for every recording.
