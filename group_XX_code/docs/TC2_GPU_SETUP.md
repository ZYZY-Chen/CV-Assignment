# TC2 GPU Environment and Input Acceptance

This guide uses the **TC2 GPU Experiment Protocol** display name and `tc2_gpu` entry points. See [TC2_GPU_NAMING.md](TC2_GPU_NAMING.md) for the mapping to the unchanged frozen protocol. Future setup records use `run/setup_tc2_gpu/`; completed `run/setup_v2/` records remain unchanged and may be read for readiness. The installed `ca6129_v2_setup` directory and `ca6129-ad-v2` environment are existing compatibility addresses, not new workflow names. Sections 6.5-6.9 retain historical commands, filenames, and snapshot paths as recorded; the naming change does not repeat those operations.

Step 2 passed final combined acceptance on 2026-10-19, preparing the cluster environment, raw data, and pretrained weights for the subsequent corrected experiments. The final job was 43950, with state COMPLETED / 0:0 and `step_2_complete=true`; complete evidence is in section 6.9. The acceptance tool reads inputs and saves check records. It does not install software, download or repair data, extract caches, fit models, or modify V1 results or the frozen protocol.

After approval of the supplementary design in section 6, separate preparation scripts created a dedicated environment and restored inputs within the specified personal directory. Section 6.7 describes the approved source supplement. Hardware job 43939, environment preparation job 43940, input preparation job 43945, and final combined acceptance job 43950 all passed. The staged preparation history is retained below; section 6.9 and setup_status.json establish the current completion status.

Connect to `huajie001@10.96.189.12:22` using SSH. The user has confirmed password login in a terminal; this does not automatically authenticate a separate new noninteractive SSH connection. The user manages passwords and private keys in the local terminal or client, outside project files.

## 1 Preparation discovery and input configuration

[tc2_setup.json](../configs/tc2_setup.json) stores verified connection details, environment, directories, partition, QoS, and final acceptance status. During discovery, null remote fields mean unverified. Do not guess the account's Home path, environment name, or data location. The following queries retain their status at the time of discovery.

The user's terminal query at 06:22 SGT on 2026-10-19 confirmed Home `/home/mcaai/huajie001`, partition `MGPU-TC2`, and QoS `normal`. That QoS limits each user to `cpu=10,gres/gpu=1,mem=30G`, at most two jobs, and a six-hour maximum per job. The partition's `infinite` setting does not override account QoS time limits. The planned acceptance request of 1 GPU, 2 CPU, 4 GB, and 15 minutes fits these limits; continue running one GPU acceptance job at a time.

The available modules included `anaconda/25.5.1`, but it had not been loaded in that terminal session and no Conda environment list had yet been obtained. A search for candidate projects and data directories within three levels of the personal Home returned no results; this does not establish that all raw data or environments are absent. `df` reports shared filesystem free space, not a personal storage quota. GPU, driver, dependencies, data, and weights still required verification at that point.

Limit remote preparation to `ca6129_v2_setup` under the verified personal Home. Inspect any existing directory before first creation; verify existing files before reuse instead of overwriting them. Reuse existing projects and data as read-only inputs, limiting access to the personal Home and explicitly authorized shared directories.

After login, first run these administrative queries and populate the preparation configuration from their output:

```bash
pwd
mytcinfo
module avail anaconda
module load anaconda/25.5.1
conda info --base
conda env list
ls -la "$HOME"
```

These queries neither inspect GPUs nor run models. GPU discovery, dependency imports, and backbone execution belong in SLURM compute jobs. If an existing environment has missing packages, version conflicts, or missing inputs, list the exact changes, update the design, and obtain confirmation before installing or downloading anything.

The next discovery round at that time required loading the module, querying the environment list and base packages, checking personal quota, and checking whether `.conda/envs`, `.cache/torch/hub/checkpoints`, and `ca6129_v2_setup` existed. The configured preparation directory was a target derived from the actual Home, not yet created or inspected; the environment prefix and input paths remained null.

That follow-up output was subsequently received: `anaconda/25.5.1` loaded successfully, Conda base was `/apps/anaconda3-2025.06-0`, and the environment list contained only base, running Python 3.13.5. The filtered package list showed NumPy 2.1.3, SciPy 1.15.3, scikit-learn 1.6.1, Pillow 11.1.0, pandas 2.2.3, matplotlib 3.10.0, PyYAML 6.0.2, and tqdm 4.67.1, without torch/torchvision. The user's `.conda/envs`, `.cache/torch/hub/checkpoints`, and `ca6129_v2_setup` did not exist. The output supplied no personal quota result, and the GPU remained untested. These findings do not establish the absence of unregistered environments or inputs outside the search scope.

## 2 Acceptance tool and required files

[check_tc2_gpu_setup.py](../scripts/check_tc2_gpu_setup.py) supports three modes:

| Mode | Checks | Execution location |
|---|---|---|
| inputs | Frozen manifests, data/mask hashes, weight hash, and old cache metadata | Local CPU, or a compute node together with other checks |
| environment | Actual dependencies, driver, GPU, and a small FP32 CUDA operation | Linux SLURM compute node |
| all | Complete input checks, environment checks, and a backbone forward pass using verified weights | Linux SLURM compute node |

Run after placing the following structure in the preparation directory. Include only files required for acceptance; historical results and caches need not be copied:

```text
ca6129_v2_setup/
  configs/protocol_v2.json
  configs/tc2_gpu.json
  configs/tc2_setup.json
  manifests/manifest_mvtec_ad_bottle.json
  manifests/manifest_mvtec_ad_cable.json
  manifests/manifest_mvtec_ad_capsule.json
  manifests/manifest_mvtec_ad_screw.json
  manifests/manifest_mvtec_ad_tile.json
  manifests/manifest_mvtec_ad_wood.json
  manifests/manifest_mvtec_loco_juice_bottle.json
  manifests/manifest_mvtec_loco_screw_bag.json
  scripts/check_tc2_gpu_setup.py
  scripts/slurm/check_tc2_gpu_setup.sh
  run/setup_tc2_gpu/
```

Raw data and weights may remain in verified existing locations; put absolute paths in `remote.datasets_root` and `remote.weights_path`. The eight manifests and protocol must match the frozen local files byte for byte. The tool verifies their fingerprints first and stops on disagreement without rebuilding splits.

GPU modes also require verified Home, preparation directory, environment prefix, partition, and QoS. Run the checker only from the `ca6129_v2_setup` copy under the verified personal Home. It checks the actual Python prefix and SLURM partition to avoid writing acceptance records or environment exports into the original project.

## 3 Data and weight checks

The fixed manifests require 3650 images and 1019 mask files. Record each file's expected SHA-256, actual SHA-256, size, and status, distinguishing matches, missing files, hash mismatches, read errors, and out-of-scope paths. Extra dataset documentation is not required to reach these counts and must not be counted as images or masks.

inputs/all mode stops explicitly if the data path is unset. It does not search other users' directories. Read only the metadata of old FP16 caches, mark them ineligible for TC2 GPU caching, and preserve their contents.

Weights are fixed to `ResNet18_Weights.IMAGENET1K_V1`, with the official file identified by the [torchvision ResNet18 definition](https://github.com/pytorch/vision/blob/v0.26.0/torchvision/models/resnet.py). Verify the full SHA-256, require its `f37072fd` prefix from the official filename, and load the file on a compute node to establish model compatibility. Record the actual local file's full hash rather than inventing one.

Create the backbone with `weights=None`, then explicitly load the verified file to prevent automatic torchvision downloads. Use a single `1x3x256x256` FP32 zero tensor for the forward pass, checking only the three layers' shapes, precision, and finite values. This is not a detection or localization experiment. Expected shapes are `layer1=[64,64,64]`, `layer2=[128,32,32]`, and `layer3=[256,16,16]`, in channel, height, width order.

## 4 SLURM acceptance jobs

[check_tc2_gpu_setup.sh](../scripts/slurm/check_tc2_gpu_setup.sh) runs only within an existing SLURM job and stops if invoked directly on the head node or local machine. It preserves the scheduler's `CUDA_VISIBLE_DEVICES` and activates the existing Conda environment prefix through the verified Anaconda module, without modifying `.bashrc` or the environment contents.

The initial request is one node, one task, 1 GPU, 2 CPU, 4 GB host memory, and 15 minutes. Supply the partition and QoS from actual account queries instead of hardcoding user-guide examples. Revise the design before submitting a request that exceeds verified quotas. Run one GPU acceptance job per account at a time.

After verifying the account, environment, and paths, submit environment and then all checks. Submit from the preparation directory and explicitly place outputs there. Assign the following variables from actual query results first:

```bash
mkdir -p run/setup_tc2_gpu
sbatch --partition="$verified_partition" --qos="$verified_qos" \
  --export="ALL,TC2_ANACONDA_MODULE=$verified_anaconda_module" \
  --output="$PWD/run/setup_tc2_gpu/slurm-%j.out" \
  --error="$PWD/run/setup_tc2_gpu/slurm-%j.err" \
  scripts/slurm/check_tc2_gpu_setup.sh "$verified_environment_prefix" environment
```

After environment checks pass and data/weight paths are complete, submit final acceptance with the same resources and `all` as the final argument. Local CPU results cannot replace environment/GPU checks; unavailable CUDA does not silently fall back to CPU.

For a local read-only inputs check:

```text
python -B scripts/check_tc2_gpu_setup.py --mode inputs --datasets-root <verified-data-root> --output-dir run/setup_tc2_gpu/<new-check-id>
```

The local check does not import torch. Use a fresh check ID each time; the tool refuses to overwrite a nonempty check directory. Even when every file matches, inputs mode establishes only input readiness and does not mark step 2 complete.

## 5 Records and acceptance

Save check records in `run/setup_tc2_gpu/<check-id>/`, separately from the formal `run/tc2_gpu/` experiment directory enabled in step 5.

| File | Record |
|---|---|
| connection_info.txt | Actual connection/authentication status, without passwords or private keys |
| qos_info.txt | Resource information queried through this user's account |
| data_audit.json | Complete, missing, and mismatched inputs, plus old cache audit |
| weights_info.json | Actual location, full hash, and verification status of the specified weights |
| environment.json | Actual Python, dependencies, driver, GPU, and check results |
| gpu_info.txt | GPU operations, FP32 settings, and backbone checks |
| versions.txt | Actual Python and dependency versions |
| setup_status.json | Completed, incomplete, and blocking conditions; missing checks are not reported as passed |

After GPU environment checks pass, export `environment-tc2.yml` and `requirements-tc2-lock.txt`, excluding personal prefixes, Conda environment variables, and authenticated package URLs. Stop and report differing existing lock files instead of overwriting. Do not create apparently valid empty locks or example version lists before verification.

Step 2 completes only when all-mode input, weight, environment, GPU operation, backbone forward, and environment-export checks pass. Preserve results and proceed through supplementary design and confirmation if dependencies are incompatible with the measured driver, inputs are missing, or hashes disagree.

Steps 3 through 5 repair evaluation, methods, and execution. Step 6 then generates FP32 feature caches and runs end-to-end pilots for both methods.

## 6 Step-2 supplement: create an environment and restore inputs (approved)

The user explicitly approved the step-2 supplementary changes and requested that subsequent remote commands follow the local `output/tc2_readonly_check.ps1`, automatically saving output locally. This design was approved; actual completion still requires returned evidence. Previous acceptance requirements and data splits remain unchanged. SLURM copies submitted scripts into job staging, so all three SLURM entry points locate and validate the preparation directory using `SLURM_SUBMIT_DIR`, correcting their earlier use of the script location. Change into the preparation directory before submission.

### 6.1 Order and stop conditions

1. Check that personal Home, preparation directory, and existing targets still agree with discovery. Record storage-quota queries and filesystem free space, explicitly marking an unavailable quota as unknown. Create preparation content only under `/home/mcaai/huajie001/ca6129_v2_setup`. Inspect existing contents and stop on conflicts without overwriting or deleting. Upload the frozen protocol, eight manifests, acceptance scripts, a read-only copy of existing `requirements-lock.txt`, and the supplementary scripts listed here.
2. Submit a short hardware job first: `MGPU-TC2` / `normal`, one node, one task, 1 GPU, 2 CPU, 4 GiB, 15 minutes. Record only GPU model, memory, driver, OS architecture, and glibc. PyTorch installation is not required first; do not query the GPU on the head node. Use Linux x86_64, glibc >=2.28, and driver >=570.26 as conservative gates for this cu128 installation. Stop and discuss another version plan if unmet; do not change the system driver. Subsequent CUDA checks still establish actual GPU support for the chosen software.
3. After the hardware gate passes, create the dedicated Conda environment `/home/mcaai/huajie001/ca6129_v2_setup/envs/ca6129-ad-v2`. Do not install packages into shared `/apps` base. Use conda-forge for Python 3.10 and pip>=24; install `torch==2.11.0+cu128` and `torchvision==0.26.0+cu128` from the official cu128 index before installing the remaining dependencies pinned by the existing lock. Inspect dependency resolution first. Preserve logs and stop on conflicts, missing packages, or network errors without independently upgrading, downgrading, or switching mirrors.
4. Restore the eight fixed raw-data categories: bottle, cable, capsule, screw, tile, and wood from MVTec AD; juice_bottle and screw_bag from MVTec LOCO AD. Verify any discovered or user-supplied complete copy against frozen hashes before reuse. Otherwise obtain the original packages through MVTec's official entry points. If direct links fail, download the same package from the official website and upload through the user's local SSH/SFTP; do not switch to third-party mirrors automatically. Use the data under CC BY-NC-SA 4.0 for this course. Extract into `datasets/{mvtec_ad,mvtec_loco}` under the preparation directory. Validate archive paths, reject links and out-of-scope members, and do not overwrite damaged or conflicting files. Restoring complete official directories for these eight categories is permitted; acceptance checks only the frozen manifest's 3650 image and 1019 mask hashes, without resplitting.
5. Download weights from `https://download.pytorch.org/models/resnet18-f37072fd.pth` to `weights/resnet18-f37072fd.pth` under the preparation directory. Record source, size, and full SHA-256 and verify the fixed `f37072fd` prefix. Download to a temporary file and publish only after verification; verify rather than overwrite existing files.
6. Run the existing environment and all acceptance jobs in order. Dependency imports, FP32 CUDA operations, and the backbone forward pass run inside SLURM. Export the actual Conda/pip locks after checks pass and return logs and acceptance records. Mark step 2 complete only when all-mode acceptance passes every check.

### 6.2 Dependencies and preparation jobs

The dedicated environment uses the following top-level targets, retaining project dependency versions rather than those installed in shared base:

| Package | Target |
|---|---|
| Python | 3.10; record the actual patch version in acceptance exports |
| torch / torchvision | 2.11.0+cu128 / 0.26.0+cu128 |
| NumPy / SciPy | 1.26.4 / 1.12.0 |
| scikit-learn / Pillow | 1.7.2 / 12.3.0 |
| pandas / matplotlib | 2.2.3 / 3.10.9 |
| PyYAML / tqdm | 6.0.3 / 4.70.1 |

The PyTorch version pairing and cu128 source were checked against the [official previous-version installation instructions](https://pytorch.org/get-started/previous-versions/). The driver gate follows the [NVIDIA CUDA 12.8 GA driver table](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html). It is a conservative condition for this design, not a claim that every lower driver is incompatible with all CUDA software.

Installation and data extraction run as separate SLURM preparation jobs: one node, one task, 2 CPU, 8 GiB, one hour, preferably without a GPU. If the partition explicitly requires one, request 1 GPU with the same other resources. Submit one preparation or acceptance job at a time and use at most 1 GPU at any time. Preserve logs and resumable temporary packages on timeout or insufficient resources; do not automatically increase resources or retry repeatedly. GPU acceptance retains the approved 1 GPU, 2 CPU, 4 GiB, and 15 minutes.

Limit temporary packages, transfer records, Conda/pip caches, and temporary files to `_downloads`, `_package_cache`, and `tmp` within the preparation directory. Conda may register the environment in the user's `~/.conda/environments.txt`; permit only its normal appended registration while preserving existing entries. Do not run `conda init` or change shell startup files. Stop on insufficient storage without deleting existing data or environments.

### 6.3 File and directory scope

In addition to the approved step-2 configuration, documentation, README, SLURM acceptance entry-point directory correction, actual environment exports, and `run/setup_tc2_gpu` records, this supplement adds four source files:

| New file, relative to group_XX_code | Responsibility |
|---|---|
| scripts/slurm/probe_tc2_gpu_hardware.sh | Short hardware job without a PyTorch dependency |
| scripts/slurm/prepare_tc2_gpu.sh | Dispatch environment / inputs preparation within SLURM |
| scripts/prepare_tc2_gpu_environment.sh | Create the dedicated environment, pin dependencies, and limit cache/log locations |
| scripts/prepare_tc2_gpu_inputs.py | Obtain official inputs, extract safely, download weights, and verify file hashes |

New remote content is limited to `envs/ca6129-ad-v2`, `datasets`, `weights`, `_downloads`, `_package_cache`, `tmp`, acceptance files/logs within the preparation directory, and the Conda personal registration above. If official website downloads require a local relay, stage packages in local `group_XX_code/run/setup_tc2_gpu/<check-id>/transfer`. Upload only the eight categories' original packages and specified weights, without historical results or caches. Do not automatically delete relay packages after transfer.

Preserve existing environment files, the old downloader, algorithms, metrics, runner, frozen protocol, eight manifests, and V1 outputs. This supplement neither installs Anomalib nor generates feature caches, fits models, enables formal `run/tc2_gpu` outputs, or writes the report. The user continues entering SSH passwords in their own terminal; do not add or change SSH keys, agents, or configuration. That terminal performs transfers and submissions requiring interactive authentication; the assistant prepares the scoped files/commands and verifies returned evidence.

### 6.4 Local operation and output retrieval (additional user requirement)

Add local `output/tc2_gpu_setup.ps1` while preserving the reference script. OpenSSH continues reading passwords directly. The default `Probe` action verifies personal Home and target paths, uploads only allowed files, verifies hashes, and submits the short hardware job, without installing packages or obtaining data. First-time publication uses separate SSH preflight, SCP upload, and SSH submission connections and may request the password more than once.

Use the same script's `PrepareEnvironment`, `PrepareInputs`, `CheckEnvironment`, and `CheckAll` actions in stages. Preparation requests default to zero GPUs; use `-PreparationGpu 1` only if the partition explicitly rejects jobs without GPUs. `Collect -JobId <id>` reads status and retrieves outputs without submitting or retrying jobs. `UploadInputs -InputDirectory <directory>` uploads only filenames matching the eight fixed category packages or specified weights into `_downloads`; existing files must have identical hashes.

Each operation creates local `output/tc2_gpu_setup_<timestamp_id>/terminal.txt` and retrieves remote `run/setup_tc2_gpu` records, logs, configuration, and any actual lock exports into its `remote` directory. Transfers use a separate Base64 archive section in SSH output; terminal logs retain only the archive summary. Verify archive SHA-256 and allowed member paths before extraction. Do not retrieve datasets, environments, pretrained weights, or feature caches as log attachments.

After submission, wait up to approximately 40 seconds for the current snapshot. Queued or running jobs remain incomplete; use Collect again rather than treating successful submission as passed acceptance. An environment-check exit code 2 may mean step 2 is not yet fully complete. Inspect environment_ready, environment_export, and related fields instead of relying only on the SLURM exit code. Installation/input preparation still follows the prerequisites and stop conditions in this section.

The initial local Windows PowerShell command was:

```powershell
& 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1' -Action Probe
```

If local policy blocks that script, use this process-only alternative:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1' -Action Probe
```

Do not paste these commands into remote Linux. After the assistant verifies hardware results, use the same local entry point for `PrepareEnvironment`, `PrepareInputs`, `CheckEnvironment`, and `CheckAll`, in order. For an unfinished job, add `-Action Collect -JobId <returned-numeric-id>` to retrieve its new status without resubmitting that stage. Preserve failures from official direct links first. Completed official packages or specified weights may be uploaded using `-Action UploadInputs -InputDirectory <local-package-directory>` before continuing input preparation.

### 6.5 Verified progress history

The user returned `output/tc2_setup_v2_20261019_065131_7cb9d616/terminal.txt`. Hardware job `43939` completed on `TC2N01` at 06:51:58 SGT on 2026-10-19, with SLURM state `COMPLETED / 0:0`. The actual GPU was an NVIDIA A40 with 46068 MiB and driver 570.148.08; the system was Linux x86_64 with glibc 2.34. All hardware gates passed. CUDA tensor operations and the backbone forward pass had not yet been tested.

The initial preparation directory had been created, and all 17 uploaded files reported SHA-256 OK. The returned archive's full hash was `3C4BF5352C5304BDEE88AE088CAFDB25D2CF44DAB9BB7E2D28F81B8D6FF1904A`; all five extracted records matched the archive individually. Personal storage quota was still unavailable; 8.9T was shared filesystem free space.

Environment preparation job `43940` was submitted with the planned 2 CPU, 8 GiB, one hour, and no GPU by default. The user subsequently returned `output/tc2_setup_v2_20261019_065531_0283f854/terminal.txt`, showing it `RUNNING` on `TC2N01` after 39 seconds. Preflight passed and the Conda dry-run resolution plan reported success, but no installation-completion record existed; planned package versions could not yet be treated as installed. Both stdout and stderr were empty in that snapshot.

That archive's SHA-256 was `0D68D5A83091D9629B5C886A46217791F1B4C4A11ADC7E474F0FCADC96FE249C`, and all 11 extracted records matched. The next action then was only `Collect -JobId 43940`, without resubmitting environment preparation or beginning data restoration. Existing remote acceptance files did not need uploading again.

The later `output/tc2_setup_v2_20261019_065834_e0fda803/terminal.txt` snapshot showed job 43940 still RUNNING after 2 minutes 59 seconds, installing torch, torchvision, and CUDA dependencies. Its installation plan specified 2.11.0+cu128 / 0.26.0+cu128, stderr was empty, and neither preparation_status.json nor a failure marker existed yet. The archive SHA-256 was `8958F6888AB24878388747548A1ECC747248487F4A4F113CF8FE596B13F1C274`, with 12 matching records. Continue waiting and Collect the same job instead of resubmitting installation.

The subsequent `output/tc2_setup_v2_20261019_070538_5b0fa3c0/terminal.txt` and structured records confirmed job 43940 as `COMPLETED / 0:0` in 5 minutes 56 seconds. The dedicated prefix was `/home/mcaai/huajie001/ca6129_v2_setup/envs/ca6129-ad-v2`. All ten actual top-level package versions matched section 6.2, pip check reported `No broken requirements found.`, and stderr was empty. The archive's full hash was `9B38B44D0D9E4E12E63FE7546CD232F60FD8DC4ED05A8D9ABD8DBE59259ADE72`; all 14 records matched.

The next action then was `PrepareInputs` to restore the eight frozen categories and specified weights and verify manifest hashes. Successful package installation did not establish CUDA acceptance. Final environment locks were not yet exported, and no cache extraction, fitting, or formal experiments were started. Step 2 remained incomplete at that point.

### 6.6 Conda activation compatibility fix

The user returned `output/tc2_setup_v2_20261019_070807_e3560acc/terminal.txt`: input preparation job 43943 ended as `FAILED / 1:0` within three seconds. Shared base's `qt-main_activate.sh` read an unset `QT_XCB_GL_INTEGRATION`, triggering the entry point's `set -u`. Failure occurred before the input-preparation Python program started; the successful installation in job 43940 remained valid.

The fix was limited to the two approved SLURM entry points, `scripts/slurm/prepare_tc2_v2.sh` and `scripts/slurm/check_setup_v2.sh`. Temporarily use `set +u` only during Conda hook evaluation and activation, then restore `set -u`, retaining `set -e` and pipefail throughout. Capture the hook in a variable first so a failed hook command also terminates correctly. Preserve shared Qt/Conda files, installed dependencies, the data protocol, and experiment code.

Add `RepairActivation` to the existing local PowerShell entry point, transferring only those two corrected scripts. Before replacement, require remote hashes to match either their known original publication values or this fix; stop on other contents. First back up both old files and a change manifest to remote `run/setup_v2/activation_fix_<id>/`. Apply the fix and resubmit one inputs job with the original resources only after confirming no active jobs and that the latest inputs preparation failed at the recorded activation stage before entering Python. Retrieve logs locally. This action neither rebuilds the environment nor resubmits installation, and it does not repeatedly retry downloads. Subsequent input/network issues follow the existing stop conditions.

Regression validation covered reproduction of the unset-variable failure with the original activation fragment, handling of the same hook class with the corrected fragment, restoration of nounset, termination on hook/activation failure, no writes on pre-replacement hash conflicts, and command rendering/output retrieval for the local fix action. Actual remote success still required returned evidence.

The user returned `output/tc2_setup_v2_20261019_071513_90e03083/terminal.txt`: both entry points had been deployed and job 43944 entered the input Python program, establishing that activation was fixed. That job then ended as FAILED / 2:0 in five seconds because the first bottle official legacy direct link returned HTTP 404. Do not rebuild the environment or blindly retry the same link. The archive SHA-256 was `993910EF013A6A0A17D5C365ED8F2909A2263C16500EE16A72582CCEEBB4AFE3`. Step 2 remained incomplete.

### 6.7 Data-source supplement (approved)

After consulting the project's `datasets/README.md`, the user explicitly approved the step-2 data-source supplement. This section replaces only the direct-official-delivery restriction for AD in section 6.1, item 4. All other environment, resource, split, and acceptance conditions remain unchanged. Do not automatically search for or switch to other mirrors.

1. Use the README's fixed third-party AD repository, `micguida1/mvtech_anomaly_detection`, pinned to revision `eb692b36147a3b3f12c561b879a062104c1f20b8`. Download `mvtec_anomaly_detection.tar.xz`, 5264982680 bytes, requiring SHA-256 `CF4313B13603BEC67ABB49CA959488F7EEDCE2A9F7795EC54446C649AC98CD3D`. This hash identifies the specified mirror file; it does not replace frozen original-image acceptance. Record MVTec Software GmbH as original publisher and accurately identify Hugging Face as the third-party delivery mirror.
2. Stage the complete archive only in `_downloads`. Extract only bottle, cable, capsule, screw, tile, and wood into `datasets/mvtec_ad`. First stream-check all member paths, types, duplicates, required six-category file hashes, and destination conflicts; then extract in a second streaming pass. Do not extract the other nine categories or archive-root documentation, recompress images, or alter pixels. Stop on links, devices, traversal, missing entries, or hash conflicts. Do not overwrite existing files.
3. Retain the two original official category packages for LOCO. Local sample requests on 2026-10-19 returned HTTP 206 and valid XZ headers: juice_bottle was 655555080 bytes and screw_bag was 1102844304 bytes. This establishes sampled reachability only, not acceptance of the full archives or images. Obtain ResNet18 weights from the official PyTorch source.
4. Prefer downloads/restoration in the TC2 inputs job with the original resources. Retain one download attempt and controlled resume behavior. Do not publish mirror files with mismatching size/hash; preserve partial packages without increasing resources or changing sources automatically. If the cluster cannot obtain the fixed packages, run the same input script's download-only mode locally, staging packages in this project's `run/setup_v2/<check-id>/transfer` without extraction or importing Torch. Relay completed packages through the existing SSH upload workflow. Add the fixed complete AD archive to its allowlist while continuing to reject unknown filenames and overwrite conflicts.
5. Limit changes to `scripts/prepare_tc2_inputs_v2.py`, `configs/tc2_setup.json`, local `output/tc2_setup_v2.ps1`, this document, and `run/setup_v2` validation/evidence. Preserve the old downloader, dataset README, algorithms, metrics, dependencies, frozen protocol, eight manifests, and V1 outputs. Retain original LOCO sources in the configuration and explicitly add the approved AD mirror identity and revision, without an automatic third-party fallback.
6. Add `UpdateInputSources` to the local helper. Generate a candidate configuration from job 43944's returned configuration, changing only the approved source fields, and package it with the input-preparation script. Require the latest remote inputs job to remain the recorded 43944 / HTTP 404, successful installation, no queued/running jobs owned by this user, and both target hashes to match known old or new values. After all checks, back up both originals, publish, and submit one inputs job with unchanged resources. Stop on unknown modifications. `-ValidateOnly` creates the local payload without connecting.
7. Add `DownloadInputs` for that download-only fallback. Create a fresh transfer directory by default; reuse an old one and resume the same source only when explicitly supplied with `-InputDirectory <original-transfer-directory>`. `UploadInputs` accepts the complete AD package; neither action submits a job itself. Preserve original logs and partial packages on network failure without repeated retries. All inputs still require frozen-manifest verification of 3650 images and 1019 masks, and step 2 completes only after final environment / all GPU acceptance.

The next local command then was `tc2_setup_v2.ps1 -Action UpdateInputSources`, with SSH passwords entered by the user in the local terminal. For a running job, use only `Collect -JobId <id>` without repeating the update or resubmitting that stage.

Local validation passed: regression checks for the original input restoration; category filtering and malformed-archive rejection for the complete package; fixed-mirror identity checks; download-only behavior without extraction or Torch import; candidate remote configuration changes restricted to three source fields; two-file update backups and unknown-conflict protection; rendering and Bash syntax for 13 remote commands across ten actions; archive transfer and rejection of bad hashes/paths. The actual `UpdateInputSources -ValidateOnly` entry point also generated a local update payload without network access or submission. Full downloads and frozen-hash acceptance had not yet completed at that stage.

The user then returned `output/tc2_setup_v2_20261019_073239_2a2bf5ec/terminal.txt`. The source update had been deployed: both new hashes and old-file backups were verified, and semantic differences in the remote configuration were limited to the three approved source fields. The archive SHA-256 was `F2607938735D69E8C1A6127F4B6C02A1961D6FF7E27387C375C7664E0A16049D`, with all 32 records matching individually.

That snapshot showed inputs job 43945 RUNNING on TC2N01 after 39 seconds, in the fixed AD mirror restoration stage, with empty stderr. Neither transfers.json nor preparation_status.json existed yet, so neither a complete download nor category restoration could be inferred. Only `Collect -JobId 43945` was required next; do not repeat the source update, resubmit inputs, or start GPU acceptance. Step 2 remained incomplete.

The later `output/tc2_setup_v2_20261019_073540_1c2557d6/terminal.txt` showed job 43945 still RUNNING after 2 minutes 40 seconds, with empty stderr. The archive hash and 32 records were unchanged, without new completion/failure records. No downloaded-byte progress was reported, so neither a completion percentage nor a stall could be inferred. Wait approximately five minutes, then Collect the same job without resubmission.

`output/tc2_setup_v2_20261019_074202_446cbb69/terminal.txt` showed job 43945 still running on TC2N01 after 9 minutes 03 seconds, with empty stderr. The returned archive SHA-256 was `403729988D0CDFD913C2E63A784EAE418FA5A70B125DAC38D2A6C94D672816F6`; all 33 records matched. The new transfers.json confirmed the complete AD package's 5264982680 bytes and fixed SHA-256 and restoration of the selected six categories. The official juice_bottle package was 655555080 bytes with SHA-256 `72B36B16AE9E5308AB4257F655EDE22173B98FC8E0CE44DB8007B588753747F2` and had been restored. Logs had entered official screw_bag restoration. Final input acceptance and weight-restoration records were still absent; restoring seven categories did not complete step 2. Continue waiting, then Collect the same job.

When `output/tc2_setup_v2_20261019_074826_4ba86798/terminal.txt` was retrieved, job 43945 was still RUNNING after 15 minutes 28 seconds, with empty stderr. Its 33 records and archive hash were unchanged. Completion records still covered only the six AD categories and juice_bottle; the latest stage was screw_bag, with insufficient logs to distinguish download, extraction, and verification progress. Inputs were not yet complete enough to begin GPU acceptance. Wait approximately ten minutes and Collect the same job without changing resources or resubmitting.

`output/tc2_setup_v2_20261019_075833_86e1edef/terminal.txt` and structured records confirmed inputs job 43945 as COMPLETED / 0:0 in 21 minutes 58 seconds, with empty stderr. The returned archive SHA-256 was `DF844DFB046277CDE9DE65F2BCF0ADB11712D29CC6AF246AC1D6560EE3186622`, with 36 matching records. Local item-by-item comparison of returned data_audit.json with the original frozen manifests confirmed exactly 4669 unique paths: all 3650 image and 1019 mask hashes matched, without missing or mismatched files. All eight categories were restored; GPU acceptance had not yet run.

The official screw_bag archive was 1102844304 bytes with actual SHA-256 `4A300E12F5974A9ABDE65984BE4529175698CFCB48D3E3C1430E7CC01D839AAB`. The specified ResNet18 weight file was 46830571 bytes with full SHA-256 `F37072FD47E89C5E827621C5BAFFA7500819F7896BBACEC160B1A16C560E07EC`, passing the official f37072fd prefix check. Model compatibility still awaited a compute-node forward pass. Verified remote data and weight paths were written into the local configuration without changing sources or experiment splits.

The next local action then became `tc2_setup_v2.ps1 -Action CheckEnvironment`, using the approved 1 GPU, 2 CPU, 4 GiB, and 15 minutes to check the environment, CUDA FP32 operations, and actual environment exports. Verify environment_ready and environment_export first, then run CheckAll to accept inputs, weights, the backbone forward pass, and all conditions. Do not resubmit input preparation, redownload data, or start subsequent experiments. Step 2 remained incomplete then.

### 6.8 GPU environment results and final acceptance entry point

The user returned `output/tc2_setup_v2_20261019_080054_297ec9d5/terminal.txt`. Environment job 43949 ran on TC2N01 for 31 seconds with environment_ready=true, environment_export.ready=true, and empty stderr. Actual Python was 3.10.22, all ten target versions matched the approved plan, and pip check passed. CUDA FP32 operations passed on the NVIDIA A40; autocast, matmul TF32, and cuDNN TF32 were disabled.

SLURM reported FAILED / 2:0 because the checker returns 0 only when all-mode acceptance passes. Even successful environment checks return 2 while step_2_complete=false. This was not a CUDA failure. The mode did not request a backbone forward pass, so backbone.status=not_requested and backbone_ready=false; final CheckAll performs it. Script behavior was not changed in this round.

The returned archive SHA-256 was `71C0E8F2F5C4829649D5AB26B3DB10043F96690534AD3F8B40DCCA215B7FA0CF`, with 46 matching records. Both actual environment exports were saved to the local code root under the approved design, refusing differing existing files: environment-tc2.yml had SHA-256 `47F1DAA83A744743946C83E6DC1963B8FA7E835A4A0F7010A3B0501EF5A3DF38`; requirements-tc2-lock.txt contained 53 actual Python distributions with SHA-256 `F7B848F10FFB3F3CCEB707450B2A5FE4DCD9A6C3B489963A8932094E016840B6`. The exports contained no top-level prefix or variables fields and no authenticated URLs.

The next local action was `tc2_setup_v2.ps1 -Action CheckAll` with the same 1 GPU, 2 CPU, 4 GiB, and 15 minutes, jointly checking raw inputs, weights, environment, GPU backbone execution, and actual exports. Only all-mode step_2_complete=true completes step 2. Do not resubmit installation/restoration or advance to step 3 at that point.

### 6.9 Final step-2 acceptance passed

The user returned `output/tc2_setup_v2_20261019_080436_6b57e857/terminal.txt`. All-mode job 43950 completed on TC2N01 with COMPLETED / 0:0 in 32 seconds and empty stderr. Final status was mode=all, status=ready, step_2_complete=true; inputs_ready, weights_ready, environment_ready, backbone_ready, and environment_export.ready were all true.

The returned archive SHA-256 was `00646CDD5FC11334A28D8C52EE39D986FE3E73C77DDEB9B5052CBFDCD4913561`; all 55 records matched individually. The final data_audit.json was again checked against the frozen manifests: all 4669 unique paths, 3650 images, and 1019 masks matched. The GPU backbone loaded weights whose full SHA-256 matched the verified official file. The three FP32 feature CHW shapes were layer1=[64,64,64], layer2=[128,32,32], and layer3=[256,16,16]; shape, precision, and finite-value checks passed. Autocast and both TF32 settings were disabled.

Both actual environment exports matched job 43949 and the locally saved files. Complete original records and local cross-checks are stored in `run/setup_v2/step2_20261019_060542/all_check_job_43950/snapshot_20261019_080436_6b57e857/`. The configuration's final_acceptance, these instructions, code README, and overall step-2 status were updated to complete as approved acceptance closeout. All 388 original baseline files were checked again: only the approved code README changed; all 346 V1 result/summary files, protocol, manifests, and the user's existing .gitignore were preserved.

This acceptance establishes readiness of the GPU environment, fixed inputs, and pretrained backbone. Metrics, algorithms, runner, and subsequent experiments continue in the agreed design/execution order. At step-2 closeout, step-3 changes were not started; the assistant awaited the user's request to start step 3 before presenting its design.
