# Sandboxing and confinement

What MadCowork actually confines, per platform, and what it does not. Written
to be quotable: if a release note or a README row says more than this page,
the page is right and the claim is wrong.

## What is confined

Every child process the app starts goes through one broker, which declares an
intent (`model`, `host`, `hook`, `probe`) and resolves a policy from the
session, the workspace settings, the environment, and dev mode. Confinement
applies to those child processes. It does not apply to the backend itself.

| Platform | Backend | What it gives |
|---|---|---|
| macOS | Seatbelt (`sandbox-exec`) | Writes confined to the workspace, temp and the app-data dir; credential paths denied for both read and write; network denied unless the intent is entitled to it |
| Linux | bubblewrap (`bwrap`) | Same write confinement; credential paths masked (an empty tmpfs over a directory, `/dev/null` over a file); its own PID namespace, `/proc` and session; no network namespace at all when network is denied |
| Linux when bubblewrap cannot start | Bundled Landlock + seccomp helper 5 | Partial confinement: private workspace stage, mediated stage-only chmod, three-way publication, filesystem complement policy, IP network entitlement, host Unix sockets blocked, subreaper cleanup. Tested on x64 Ubuntu 22.04 / ABI 1 and arm64 Ubuntu 24.04 / ABI 7. See limits below |
| Linux without either usable backend | none | Execution is refused unless unconfined execution is explicitly allowed |
| Windows | Dedicated local account + native helper | Commands run from a private workspace stage with a command-unique default-deny AppContainer lowbox token, an ephemeral profile, a private desktop, a no-breakaway Job Object, trusted publication and account-scoped WFP network blocks |

## Windows

Windows uses a dedicated, ordinary local account. On first use, Settings asks
for one elevation to create the account, generate its random password, protect
the credential with machine DPAPI, install eight persistent account-SID WFP
filters (connect, listen, receive/accept and resource assignment for IPv4 and
IPv6), and add only
traverse/read-attribute access to the launching user's standard profile
directories. The state directory and credential ACLs
contain only the launching user and SYSTEM. Declining elevation leaves the
provider unavailable, so required commands are refused.

For every command, the broker copies the selected workspace into a private
stage. The helper logs on the dedicated account and creates a command-unique
AppContainer lowbox token. Windows enforces the package SID as the lowbox access
boundary; readiness is established by live access probes rather than the
`IsTokenRestricted` API, which does not classify this token consistently.
The command package SID receives access only to the private stage. Users,
Authenticated Users and Everyone are never added to that package boundary.
Existing shared ACLs, Public folders, other workspaces and a shared host temp
directory therefore do not widen the boundary.

Only the private stage and its broker-owned temp/profile directories receive
command/package ACL entries. System and Program Files runtimes keep their
installer ACLs. Before any probe or launch, the broker accepts the native
helper only from a digest-verified application bundle or a protected system
location. It resolves cmd, PowerShell, Node, Python and Git from fixed absolute
system locations, verifies the owner and every relevant ACL in the helper, and
constructs PATH only from those admitted directories. It never searches the
ambient PATH or executes a runtime from a user-writable location. HOME, USERPROFILE, APPDATA,
LOCALAPPDATA and all temp variables point into the stage. The trusted runner
starts a trusted account-side lifecycle owner outside the command Job. That
owner creates the command-unique AppContainer profile, watches the helper
through a parent-owned mutex lease, and deletes the profile through the AppContainer API after
normal exit, timeout, cancellation or a hard helper crash. Startup and repair
also reap inactive profiles whose install-specific prefix is proved by the
protected marker. The model process receives the AppContainer token and stage
environment. Child processes inherit
the same token and remain in a Job Object with `KILL_ON_JOB_CLOSE` and no
breakaway, on a private desktop.

The helper gives each command a temporary drive alias whose root is the private
stage. Git for Windows can then resolve its working directory without gaining
read access to the host volume root. Only the disposable stage ancestry gets
non-inheriting list/traverse entries, and the alias is removed when the runner
exits. Node loads the already validated npm entry point with symlink
canonicalization disabled, avoiding the same volume-root probe without adding
host access.

ACL journals record only the exact ACEs added for that command plus the pinned
volume/file identity. Normal cleanup and crash recovery remove those exact
deltas, preserving pre-existing ACEs and concurrent host ACL changes. Requests
and journals live in the disposable stage rather than the installed state
directory. Before each serialized launch, the helper scans the fixed active and
recovery stage buckets for interrupted journals, without following reparse
points, so a broker crash cannot strand a command SID on a live stage object.
Launches remain serialized while ACL and window-station changes are live.

After exit, Windows calls the same three-way preflight and trusted publisher as
the Linux staged backend. Protected absent names, unsafe Git metadata, hooks,
autoload controls and links never reach the host workspace; ordinary Git init,
add, commit and status plus local npm workflows remain usable inside the stage.
Git for Windows clone transport starts MSYS `sh`, whose global named-object
namespace is deliberately unavailable to the AppContainer. Git handling has
two explicit layers. L1 is a convenience and UX gate: for structured argv and
`extraEnv`, the broker uses deny-by-default config-key and `GIT_*`-variable
allowlists, accepts only `git.exe`, and synchronously returns a typed, localized
instruction for recognizable transport or executable-injection forms. Shell
text classification is best effort; dynamically assembled or nested cmd and
PowerShell commands can enter the stage. L2 is the security boundary: the
default-deny lowbox keeps spawned programs confined, the account WFP filters
block their network access and the publisher rejects protected or unsafe
output. Tests require those dynamic forms to terminate with failure within ten
seconds, make no loopback or LAN listener connection and publish no success
marker. A new repository or clone entering the publisher still receives the
shared new-`.git` validation before publication.
The WFP filters deny outbound connect, inbound listen and receive/accept, plus
TCP and UDP port assignment, including loopback, for both IP families. The
machine identity stores and validates the original owner SID before setup,
repair, policy removal or teardown can mutate state. Before the provider is selected, `--check`
validates the sealed credential and logon, account/SID marker, private state
ACL, traversal entries, hidden-account state, install identity and every WFP
filter's layer, action and exact SID condition. Any drift reports repair
required and fails closed.

Uninstall invokes the same helper to remove the account, filters, traversal
entries, marker and sealed credential before deleting the helper; a failed or
declined teardown stops uninstall so the repair path remains available.

## Choosing where it can write

### Developing MadCowork inside MadCowork

A running source checkout or installed app bundle cannot simultaneously be the
app's executable code and a writable workspace. Workspace tools are supposed
to be able to change files, so bytes inside that tree cannot remain a trust
root for the host process. In a packaged build the protected runtime is the
whole installation root above `resourcesPath`—on macOS, the entire
`Contents/` tree, including `Resources/app`, bundled runtimes, and
`Contents/MacOS`. The backend rejects overlap in either direction with
`SOURCE_WORKSPACE_REFUSED`, including when the workspace came from
persisted settings at restart.

Version 0.68.0 does not support using its own source checkout as a writable
workspace. Development uses two checkouts or worktrees: run the app from one,
and select the other as the writable workspace. The same refusal applies to a
saved startup workspace, a workspace PATCH, an extra writable grant, and every
configured `sandboxWritableDirs` entry. The verified source-module closure is
still enforced as a second defence. The app bundle is also in the sandbox's
never-writable set. CLI-agent worktrees are writable too: their deterministic
`getOutputDataDir()/cli-agents/worktrees` parent is always included, and each
live worktree is registered when created and revoked only when cleaned up.

External editors and coding-agent CLIs are a separate explicit capability.
Configure their absolute paths in Settings → Advanced → External programs.
MadCowork records the canonical path, device/inode identity, and SHA-256 of the
selected file, then revalidates those values, every path ancestor, and the
current writable-root set before every probe and launch. PATH discovery is only
a hint and never grants execution. POSIX ancestors are principal-aware: an
owner-write bit is accepted for uid 0 (root) or the current user; a group-write
bit is accepted only for the user's primary group or an administrative group
the user actually belongs to (`admin` / `wheel` on macOS; `sudo` / `wheel` on
Linux). Gid 0 is not a synonym for root ownership and is never pre-trusted.
World-writable, sticky, another
user's writable owner bit, and non-member writable groups are rejected. This
allows normal `/Applications` and Homebrew layouts without treating arbitrary
group-write access as safe. The model's sandbox cannot assume the user's
identity to write outside its declared roots, so these principals stay within
the same local-user trust domain as the revalidate-to-spawn premise.

The SHA-256 is always computed while selecting a program and on the first use
in each process. Later uses may reuse that process-local digest only while
`dev`, `ino`, `size`, `mtimeNs`, and `ctimeNs` are unchanged and the current
path, ancestor-principal, and writable-root checks have all passed. Any metadata
change forces a fresh digest. Under those conditions, the remaining change
between revalidation and spawn requires the local user to modify protected
state; this boundary does not attempt a separate handle-based secure launch.

The sandbox confines writes to three places: the conversation's workspace, a
process-private root with a session-private temp directory, and the app's own
data directory. `TMPDIR`, `TMP`, and `TEMP` point at that private directory;
this is the command's own temp directory bound over the shared one rather than
a grant to the host temp tree. The shared system temp root is never granted or generally readable. Bubblewrap
covers shared temp with an empty tmpfs, recreates only authorized mount points,
and exposes the current session directory writable. When an AppImage runtime is
itself `/tmp/.mount_*/`, only that exact runtime is mounted back read-only so its
executable and bundled socket guard remain available. Seatbelt denies reads of
the shared temp and the complete process-private root, then allows only the
current session, explicitly authorized temp descendants, and that read-only
runtime. Landlock uses `--hide-tmp` and reopens the current scratch; Windows uses
the command's private stage temp. Thus host temp files, another session, and
another app instance are unreadable on every backend. The process removes its
unpredictable 0700 temp root on normal exit, with OS temp cleanup as the crash
fallback. The workspace is yours to choose — it is set per conversation, so
pointing a conversation at a different folder moves the sandbox with it.

The runtime pathname guard applies the same process authorization to callback
and Promise forms of `child_process.exec` / `execFile`. Its private
`util.promisify.custom` adapter invokes the guarded callback function and keeps
Node's `{ stdout, stderr }` success shape plus those fields on errors. Callable
symbol hooks from the original unguarded function are never copied, so
`promisify(execFile)` cannot bypass the capability check.

A new ordinary conversation with no selected project does not execute from the
home directory. The worker assigns that conversation its own lazy directory
under the output root (by default `~/Desktop/MadCoworkDoc/<date>_<title>`), and
that directory becomes the command work directory. It is created only when a
tool first needs it. Selecting a project or folder keeps using that explicit
directory.

For the case that needs one more place — an output folder outside the
project, a shared drive — grant it in your **global** settings:

```json
{ "sandboxWritableDirs": ["/Users/you/Documents/reports"] }
```

Entries must be absolute, must exist, and must be directories; anything else
is dropped rather than guessed at. `/`, `/dev` and `/proc` are refused however
they arrive — as a grant, or as the workspace root, which the app also refuses
to set. On Linux a writable bind of any of them is applied after the sandbox's
own `/dev` and `/proc` and, being recursive, would shadow them back with the
host's, taking device and PID isolation with them; the binds are additionally
ordered so that even a gap in that refusal could not undo the isolation. This key is global-only for the same reason `sandboxUnconfined` is: a
workspace that could widen its own sandbox does not have one, and the settings
file itself is denied to sandboxed processes wherever you keep it — including
a custom `MADCOWORK_SETTINGS` path, which would otherwise be editable by the
very processes it governs.

Granting your home directory remains a bigger decision than granting a narrow
output folder, but it does not reopen persistent execution points. A single
policy list denies writes to shell startup files (`.zshenv`, `.zprofile`,
`.zshrc`, `.zlogin`, `.zlogout`, `.bashrc`, `.bash_profile`, `.bash_login`, `.bash_logout`, `.profile`,
`.kshrc`, `.cshrc`, `.tcshrc`), fish/Nushell/PowerShell configuration,
`Library/LaunchAgents`, Services and Workflows, XDG autostart, systemd user
units and environment.d, `.ssh`, Vim/Neovim/Emacs startup and package trees,
JetBrains/Sublime Text/Zed plugin and configuration trees, global Git config/
attributes, and VS Code/Cursor/Windsurf extension and user configuration trees.
`ZDOTDIR` and XDG overrides are included. Ambient auto-load controls are also
reserved: `BASH_ENV`, `ENV`, `PYTHONSTARTUP`/`PYTHONPATH`, Node
`--require`/`--import` and module paths, Perl and Ruby include/require paths,
plus `LD_PRELOAD` and
`DYLD_INSERT_LIBRARIES`. Only literal absolute auto-load paths are accepted.
Values containing consumer expansion (`$`, backticks, `~`, loader `@...`
tokens, and Windows `%...%`/`!...!`), relative paths, or an empty path-list
entry fail closed before a confined command starts. This is deliberate:
`BASH_ENV=$PWD/file` is expanded by a later Bash in that later working
directory, so protecting a literal `$PWD` filename or a few guessed roots is
not equivalent. `/dev/null` (and Windows `NUL`) is ignored. The independent
P15 oracle separately enforces the same refusal without importing the
production parser. macOS BTM/shared-file-list backing
stores are read-only, and Seatbelt denies Apple Events so a command cannot ask
System Events to register a Login Item instead. The deny applies even when a
listed path does not yet exist. P15 uses a separately maintained expected
inventory rather than deriving its oracle from the production list. A real Vim
startup regression proves one auto-load chain in an isolated test home.

Linux cannot express Seatbelt's per-name rule without creating mount points
for absent paths. If a conversation explicitly selects the whole home directory
as its workspace, the broker therefore keeps that HOME read-only on Linux.
Ordinary per-conversation directories and explicitly selected project
subdirectories remain writable; host-side file tools are unchanged.

A grant cannot widen what the sandbox exists to protect. Credential denials
and the trust-store protection are written into the profile after the
writable allows, so granting `~` — or even the credential directory itself —
still leaves `~/.ssh` unreadable and the trust store unwritable. The deny
wins, and there are tests that spawn real commands to prove it — including
attacks on the path itself: a hardlink to the settings file cannot be created
from inside, and renaming or symlink-swapping its parent directory does not
free the name, because the rule is re-evaluated on every access.

## What the app data directory is, and is not

Most of what the app keeps in its data directory decides what happens on the
NEXT run: `mcp.json` names servers the backend spawns at boot, the vendored
`.py` helpers are executed by the host, `plugins/` carries each plugin's trust
bit, `skills/` and `memory/` are replayed into later sessions as instructions,
`.env` is read before the bundled defaults, and `claude/` holds bridged
credentials. All of it is read-only inside the sandbox.

The writable set there is an allow-list, and it is down to one entry: the
`logs/` directory hooks are documented to write. The caches the backend fills
never needed to be on it — the backend is not sandboxed. A file nobody has
classified is read-only by default rather than writable by default.

A deny-list was tried first and was the wrong shape: it named four dangerous
files and left `mcp.json` writable, which is host code execution on the next
start. Guessing at the allow-list was wrong too — the first version included
`__pycache__`, and while a child is barred from WRITING bytecode it is not
barred from the host READING it, so a planted `.pyc` for a module the helpers
import would have been loaded on the next host run.

Everything on the list is created up front. On Linux a missing bind source is
skipped and the parent is read-only by then, so a file left to be "created on
first use" could never be created at all.

Being written by a confined process is not on its own a reason to put
something on that list. What matters is what the HOST does with the file
afterwards.

The mail account store holds each account's password in plain text, so it is
denied outright — any command could otherwise have read the credentials into
its own output. The cluster file holds no secret at all and is still not
writable, because its `host` field goes straight into the host side's `ssh`
argv: a saved `-oProxyCommand=…` is local command execution the next time the
host runs one of the helpers. The helpers now refuse a destination that could
be read as an option, wherever the record came from. Both are edited through
the app's own host-side endpoints; the confined edit paths are moving to
narrow host capabilities.

Live sockets are masked for model and hook executions. In addition, provider
policy denies AF_UNIX by family/endpoint even when IP networking is allowed;
the path list is defense in depth, not the primary boundary. `network: "deny"` is a
network namespace, and a Linux network namespace isolates only the ABSTRACT
unix socket namespace — a pathname socket is addressed through the filesystem,
which the sandbox binds. So an SSH ControlMaster socket is a working channel
to a remote host that ignores the network policy entirely, and a container
runtime socket would be a full host escape. The whole user runtime directory is masked rather than
the sockets inside it: besides the rootless container runtimes it holds the
user D-Bus socket, and systemd's user manager will start a program outside
the sandbox for anything that can talk to it. It is masked by its standard
`/run/user/<uid>` path as well as by `$XDG_RUNTIME_DIR`, because a confined
process can open the known path without reading the variable. The HPC tooling runs with the
host intent and still sees them; it is their legitimate user. On macOS,
Seatbelt always denies inbound/outbound Unix endpoints. Its fixed allowlist is
only `/private/var/run/mDNSResponder` (DNS resolution) and
`/private/var/run/syslog` (logging); neither protocol launches commands or
accepts a caller-chosen output path. `network: "allow"` therefore means
AF_INET/AF_INET6, not Screen/tmux/SSH-agent/container sockets.

Naming sockets one at a time is a deny-list that cannot be finished, though —
any host daemon listening in the shared temp directory is another one. Model
and hook executions therefore receive a session-private temp view. It is per
session rather than per command, so writing a file in one command and reading
it in the next still works, while host temp and other session/instance entries
are not readable. If that directory cannot be created, execution is refused
rather than run with the shared one, and its location is unpredictable — a
fixed path under the temp directory is something anything on the machine can
pre-create as a link. It is checked to be a directory this process owns, with
no access for anyone else, every time it is used and not only when it is made.
Bubblewrap supplies the empty mount view, Landlock hides the shared root, and
Seatbelt expresses the same boundary as ordered read deny/allow rules; the
provider-level Unix endpoint rules remain a separate defence.

A protected path that lives INSIDE a carve-out is re-protected after it: the
carve-out is a whole directory and the last rule wins, so a trust store or an
MCP config configured to sit under one would otherwise be reopened by it.

`.env` goes further than read-only — it holds provider keys, so it cannot be
read either. Nothing that runs confined needs it; the vendored helpers read
`hpc_env.json`, which is scratch.

`.env` is protected whether or not it exists, and it is deliberately never
created on your machine. Its absence is meaningful — the app loads the first
env file it finds and the per-machine one is first, so an empty one would
shadow the packaged defaults and a fresh install would come up asking for a
key it already had.

That also means a confined process cannot plant a symlink in those
directories, so the host-side checks below never face one there. That is
defence in depth, not a substitute for them.

## The app's own host helpers

### Host-path threat model

Workspace content and model-controlled sandboxes are hostile inputs. They may
create, rename, symlink, hardlink, junction-swap, or race any path they can
write, and they control every filename and metadata value read from the
workspace. They cannot directly modify the signed app bundle, app-private
state, or protected system paths; the boundary must nevertheless reject any
attempt to deceive a host-side reader, writer, or broker into crossing into
those locations.

The protected properties are bidirectional: host reads and writes must remain
inside the registered workspace (or an explicitly pinned private staging
root), and content outside that boundary must never be copied or published
back into the workspace. Explicit trusted roots fail closed; they are not
hints that permit a pathname fallback. Native helpers open path components
relative to directory handles and recheck identity after operations.

The bundled native helper is bound to its binary digest, platform, architecture,
test-gate shape, native-source digest, and deterministic build flags. A source
checkout rejects a helper built from stale source. A packaged app may omit the
native source and instead relies on the platform's app-bundle signature plus
the protected anchor containing those build and binary identities.

`server/hpc/<lane>/hpc_ssh.py` is the only helper allowed to bypass ordinary
host-process confinement. It must reuse the user's SSH configuration and live
ControlMaster socket, and it must create the owner-only `sockets/` directory;
putting it in the general sandbox would remove those exact capabilities and
break the native HPC panel. This is a single narrow exception, not a general
`host`-intent exemption.

Only `execTrustedHpcHelper()` can mint the private broker capability. Before
execution the broker resolves one canonical interpreter, then checks every
file in its platform closure manifest in both the bundled and deployed trees.
Each member must be a regular non-symlink with the expected canonical identity
and the same SHA-256 as the bundled copy. The helper runs with `-B`, inherited
bytecode writes disabled, and `PYTHONPYCACHEPREFIX` pointing at a fresh private
directory that is removed afterward. Callers cannot replace the interpreter,
script path, environment, execution mode, or capability token.

Two gates keep that exception measurable. `hpc_ssh.py --selftest` imports the
lane's complete sidecar closure, creates and checks the socket directory, reads
the SSH config and HPC environment file without emitting their contents, and reports the
Python bytecode state as one JSON line without contacting a cluster.
`scripts/verify-hpc-trusted-path.mjs` deploys the scripts from either a source
tree or a packaged app, runs that selftest through the trusted broker path,
checks the audit outcome, compares the recursive Python AST import/spawn graph
with the manifest, and proves an ordinary host invocation cannot pass every
check. Windows records the manifest comparison as `未實跑` until it has a
confinement backend capable of the two-sided runtime proof.

Before changing confinement, app-data protection, helper deployment, or the
trusted closure, run both:

```bash
npx vitest run tests/hpc-host-helper.test.mjs tests/hpc-path-guard.test.mjs
node scripts/verify-hpc-trusted-path.mjs .
```

The change is not ready if the second command does not print
`[hpc-path-gate] PASS`.

## The native tools are a separate boundary

`write_file`, `edit_file`, `save_skill` and `remember` run in the backend, not
in the sandbox. Their limits — inside the workspace, outside the blocked
directories — are enforced in the backend too, and they are enforced against
what a path RESOLVES to, not what it says.

That distinction is the whole point. Creating a symlink needs no access to its
target, so a confined process can always create one; if the host side followed
it, the sandbox would be decoration. A link inside the workspace that points
at the settings file is refused, whether the link is the last component or a
directory somewhere in the middle. Writes additionally refuse to follow a
final symlink at all, so the answer is still true at the moment of the write
and not merely when it was checked.

Where a setting is written is deliberately not where it is read from. The app
reads `.env` from several places, and in a packaged build one of them is
inside the signed bundle; settings are written to the per-machine
`~/.madcowork/.env`, which the app loads first. A write that fails is
reported, not swallowed — the in-memory value is not changed either, so the
app never shows a setting that a restart would discard.

## Allowing unconfined execution

Three ways, in the order most people should consider them:

1. Set this conversation's sandbox mode to `off`. That path never claimed
   confinement, so nothing is being weakened by surprise.
2. `MADCOWORK_ALLOW_UNCONFINED=1` in the environment, for a one-off run.
3. `"sandboxUnconfined": true` in your **global** settings file.

The third is deliberately global-only. Trusting a folder means its
configuration may take effect; it must never mean the folder can switch off
the confinement that contains it, so this key is read from the user's own
settings file and never from the merged layer.

A session set to `require` is not affected by any of these: if the platform
cannot confine, a required sandbox refuses, and that refusal has its own
error code.

## What confinement is not

- It is not per-user authorization. Anything running as this user with the
  auth token has the same access the app does.
- It is not protection against the backend itself. The broker confines what
  it launches, not its own process.
- On macOS and Linux bubblewrap, it is not a deny-default read policy.
  Credential paths are denied by name; a store not on that list is readable.
  Windows' restricted AppContainer token is deny-default outside its staged
  and runtime grants, and the Linux Landlock fallback uses a complement policy.
- It is not protection against a hardlink that already existed. The denials
  are by path; a second name for the same file, created before the sandbox
  ever ran, is a different path. What is prevented is making one from inside.
- It is not free of check-then-use races. The host-side checks resolve a path
  and then open it, and Node exposes no `openat`, so a path swapped between
  those two moments is not caught by resolution alone. `O_NOFOLLOW` closes the
  last component, the read-only app-data paths remove the directories where
  planting a link would matter most, and the remaining window needs a process
  running concurrently with the tool call. Closing it properly needs a pinned
  directory handle walked segment by segment — tracked work, not a claim to
  make today.
- Linux first probes bubblewrap 0.12.0 or newer, then the bundled Landlock
  helper. Neither backend being usable means refusal. The helper is a fallback,
  not equivalent to bubblewrap's mount/PID namespaces.

## Linux Landlock fallback

The small native helper lives in `server/linux-sandbox/landlock-helper.c`.
`bundle-landlock.mjs` builds it natively and statically on x64/arm64, without
root or external libraries. The build manifest binds its architecture, version,
source SHA-256 and binary SHA-256. Both the prebuild/beforePack gate and finished
AppImage extraction gate verify it. Electron pins its absolute path through
`MADCOWORK_LANDLOCK`; a failed version, ABI or actual enforcement probe refuses
this backend. Bubblewrap remains first choice, including on older kernels. Ubuntu 24.04
can prevent its startup with `kernel.apparmor_restrict_unprivileged_userns=1`;
Landlock needs no user namespace or change to that setting.

Filesystem policy uses Landlock rules attached to pinned O_PATH descriptors.
Read access starts at `/`, but no read rule is placed on any ancestor of a denied
path. The helper walks those ancestors with openat/O_NOFOLLOW, recursively grants
existing siblings and skips the denied branch, including when the named secret
is absent. WRITE_FILE, creation, removal and truncation are independently granted
only beneath writable roots, excluding both secrets and protected paths. Explicit
app scratch exceptions reopen only their own subtree; protections below an
exception still apply. Symlinks are never followed while constructing grants;
access through them is checked against the target by the kernel.

Landlock cannot place a creation allow on an ancestor while excluding a protected
descendant. The broker therefore never gives the command the real workspace as a
writable root. It first creates a private mode-0700 copy stage below the app's
protected data tree. The fixed `landlock-stages` parent, including both `active`
and `recovery`, is denied to every restricted command, and only the current run's
pinned workspace subtree is reopened. A startup
scavenger moves marker-verified remnants from crashed brokers into the private
recovery directory without touching a live broker's stages. The copy stage
prefers filesystem reflinks for regular files, and falls back to byte copies only
within a 1 GiB, 100,000-entry and 16 KiB-path budget. An unsupported special node
or exceeded budget refuses execution before the child starts. The command works in
the staged path, so workspace-root file/directory creation, atomic rename, a new
repository's `git add`/`git clone`, and local offline npm installation remain usable.
P2 requires every one of those operations to pass on Linux.

After exit, the same trusted preflight and publisher used by bubblewrap performs a
three-way comparison of the immutable launch manifest, complete staged tree and
current host tree. An unchanged stage never touches the host; a stage change is
published only when the host still matches the baseline; divergent changes return
an explicit host conflict without any host mutation. The host tree is rescanned
immediately before the first mutation, then every action performs the
descriptor-backed compare-and-swap described below.
Existing Git metadata,
Git selectors and other protected controls may be changed inside the stage, but a
change refuses the whole publication and forces a nonzero command result. A newly
created `.git` is publishable only after the independent validation described
below. This also removes the prior concurrent-host-Git selector window: staged
control files are not host-visible during execution. The AI `write_file` and
`edit_file` tools execute host-side (`tools.mjs` / `devTools.mjs`,
`writeFileNoFollow`) and do not inherit the command's Landlock domain; they still
enforce path, permission, protection and read-before-edit rules.

There is no mount remapping. For untrusted intents the shared temp root is excluded
from reads/writes and the granted session temp is passed as TMPDIR/TMP/TEMP. Explicit
workspace/grant descendants remain accessible. Programs hard-coding shared `/tmp`
can fail. `/proc`, `/sys` and raw `/dev` access is denied; only null/zero/random/urandom
are individually permitted. There is no PID namespace. Filesystem metadata remains
observable through stat (not file contents); pre-existing hardlink aliases and
pre-existing bind-mount aliases, and concurrent host-side renames are not solved by path exclusion.
A bind alias beneath an allowed subtree can expose denied contents; an explicit
grant on a bind alias of the denied inode can even reopen the original name.
FUSE, overlayfs and idmapped aliases have not been exhaustively tested. The health
check does not automatically discover filesystem aliases. The complement protects
named paths under the measured mount layout, not every alias to their contents.
The copy stage is deliberately independent of `fuse-overlayfs`; hosts may still
enable bubblewrap's user namespace support to obtain the stronger backend.

Seccomp validates the native audit architecture and rejects x32 syscall numbers.
It blocks ptrace/process_vm_readv/process_vm_writev, io_uring, descriptor stealing,
namespace changes, host signals, System V/POSIX message IPC and mutation operations
that Landlock does not mediate. `chmod` variants are handled by seccomp user
notification: the trusted supervisor resolves them beneath the pinned current-stage
descriptor, rejects setuid/setgid/sticky bits and non-regular/non-directory targets,
and performs only a filtered `0777` mode change. Requests outside the stage fail;
chown, xattrs, timestamps
and mutating device ioctls return errors. Only harmless fd mode ioctls are allowed. Cross-directory rename/link (REFER) and device
creation remain denied. These restrictions also apply inside writable directories;
some tools, including permission-preserving copies, can fail.

With network denied, socket() is forbidden. With network allowed, only AF_INET and
AF_INET6 socket() are permitted. AF_UNIX socket() is denied in both modes, so no
pathname/abstract host socket is reachable, including a socket not on a denylist.
Anonymous AF_UNIX SOCK_STREAM socketpair remains available for local child IPC;
datagram socketpairs are denied because they can be reconnected to a host socket.
The helper closes every inherited fd above 2. Standard streams accept pipes,
anonymous connected Unix stream pairs used by Node, /dev/null, and write-only
regular output files supplied by the broker. Other standard descriptors are replaced
with /dev/null. This does not offer access to host SSH agents, Docker, D-Bus or Unix
socket services, even with IP networking allowed.

The same native helper's narrow `--socket-guard` mode runs inside bubblewrap.
It applies only the AF_UNIX/socketpair filter, CLONE_PARENT/namespace guard and
subreaper lifecycle; bubblewrap retains filesystem/mount/PID-namespace policy.
If this helper is missing or fails its live probe, bubblewrap is not selected.
There is no denylist-only or unconfined fallback.

Before exec the child enables no_new_privs, installs Landlock and seccomp, then
runs the original argv (or `/bin/sh -c` for an existing shell request). The helper
stays outside the child domain as a nondumpable subreaper. After command exit or
SIGTERM/SIGINT/SIGHUP it repeatedly kills and reaps its own direct children;
orphaned descendants, including setsid children, are adopted and killed in turn.
CLONE_PARENT and namespace creation are blocked; clone3 returns ENOSYS for libc
fallback to the checked clone syscall. Attached runs receive SIGTERM when their
backend parent dies; detached runs retain the existing survive-restart contract.
**Direct SIGKILL of the supervisor cannot be handled**: its immediate child has a
parent-death kill signal, but arbitrary descendants after forced supervisor death
are not guaranteed. Broker timeouts/aborts send SIGTERM first and were tested with
setsid grandchildren. This limitation is another reason to retain a partial grade.

| Queried ABI | File truncation enforcement | Reported capability |
|---|---|---|
| unavailable/disabled | No helper backend | Refuse if bubblewrap also fails |
| 1–2 | Landlock WRITE_FILE on write-open; seccomp rejects truncate/ftruncate, read-only O_TRUNC and openat2 | Partial; additional tool compatibility restrictions |
| 3–4 | Native Landlock TRUNCATE | Partial; complement/namespace/metadata/cleanup limits remain |
| 5+ | Native TRUNCATE and handled IOCTL_DEV (not granted) | Partial; same remaining limits; IP/Unix filtering still uses seccomp |

The actual ABI is queried with landlock_create_ruleset VERSION, never inferred from
a kernel version. As tested on 2026-09-29, dell (5.15 x64) reports ABI 1 and gx10
(6.17 arm64) reports ABI 7. ABI 2–6 individually and other distributions have not
been runtime-tested. A successful availability probe proves the primitives start,
not that every application works or that the backend has earned a strong grade.

The implementation follows the kernel's [Landlock documentation](https://docs.kernel.org/userspace-api/landlock.html)
and [seccomp architecture guidance](https://docs.kernel.org/userspace-api/seccomp_filter.html).
The repository-local Codex Linux sandbox was consulted for the fallback shape and
network syscall risks; its full Rust implementation was not copied.

## Checking the sandbox

Open **Settings → Safety and sandbox → Sandbox check** and choose **Check
sandbox**. Fifteen live probes run through the execution broker, with a
controlled workspace, synthetic credential canaries and temporary listeners.
The report includes the backend and version, check time, individual results and
one of `strong`, `partial`, `none`, or `broken`. A file-boundary failure is
`broken`; `partial` requires the file checks to pass. An unavailable backend is
`none` only when the broker demonstrably refuses execution. A failed workspace
write is always a fault, never proof of protection.

Checks run in a separate process with controlled settings, required confinement
and denied network access (P8 uses the network-entitled host intent). They test
the backend's confinement capabilities, not a claim that a conversation with
sandbox mode **off** is confined. The probes use only a new, random app-data filename which is removed
immediately; credential files are never read. The normal broker may load plugin
metadata while resolving settings. Results contain status codes, booleans and disposable-victim resource properties, not child output or canaries.
P7 explicitly records an external-network skip when its host control cannot
connect. P10 observes normal and detached grandchildren after both timeout and
abort; on Windows it also attempts a native `CREATE_BREAKAWAY_FROM_JOB` child.
Its heartbeat processes have a bounded lifetime even when confinement fails.
Existing defects are reported, never converted into passing checks.

P14 tests host-process isolation against a fresh, same-user victim for each
operation: SIGTERM, SIGUSR1 and setpriority on POSIX; Linux also tests prlimit,
fcntl F_SETOWN + O_ASYNC (SIGIO), and sched_setaffinity. Windows uses
OpenProcess with PROCESS_TERMINATE / PROCESS_SET_INFORMATION, followed by
TerminateProcess / SetPriorityClass. Every operation first proves a real effect
without confinement, then checks a separate victim through the model broker.
A passing check requires denial, continuing heartbeat, and unchanged limits,
priority and CPU affinity. Missing tools or failed controls are failures, never
passes. Python stdlib supplies the native calls (bundled Python, an explicit
MADCOWORK_PYTHON, or system Python); no compiler or third-party package is needed.
A supervised host guardian retains the child until the attempt finishes so its
PID cannot be reused. Victims expire after 12 seconds; guardians after 15 seconds
and clean up only their own child. Neither the API nor saved results supply PIDs.
The Settings table includes a localized P14 description; the CLI prints its name.
On macOS the Seatbelt profile denies `system-sched`, so a confined command cannot
use `setpriority`/`renice` against another same-UID process. It also denies
`process-info-setcontrol` and `process-info-dirtycontrol` for other processes
while retaining those controls for the sandboxed process itself, following the
self-only carve-out used by Apple system profiles. The scheduling denial is
global: `nice` may warn that it could not change its own priority but must still
run the requested command.

Each app version starts a background check once and saves the result at
`MADCOWORK_HOME/sandbox-self-test.json`. Startup remains non-blocking. A failed
check can be retried with the button; simultaneous requests share one run.
Protection below the platform expectation is shown in Settings and beside the
permission-mode badge.

The authenticated API is `GET /api/sandbox/self-test` for `{result, running}`
and `POST /api/sandbox/self-test` to await a fresh report. Both require the
backend token even from loopback. For the packaged server, prepend
`/api/backend`:

```sh
madcowork sandbox check --attach http://127.0.0.1:5180/api/backend
```

Without `--attach`, the CLI uses the running packaged server on
`MADCOWORK_PORT` (default 5180). Use the instance's `MADCOWORK_HOME` so the CLI reads its token, or supply
`MADCOWORK_AUTH_TOKEN` in the environment. No token belongs on the command line.
The CLI prints the probe table and exits nonzero below expectation. Release
scripts run this check against the isolated **packaged** startup instance before
stopping it. Headless Linux cannot waive sandbox verification by skipping launch.
The shared policy is `server/backend/sandboxExpectations.mjs`: macOS, Windows
and Linux bubblewrap require strong protection. Landlock requires partial with
all 15 probes passing, including P14; a missing or failed probe still blocks
release. The shared schema requires P1–P15 exactly once on every platform; a
legacy 14-probe report cannot pass. P15 covers persistence-location writes.

Battery case: `FLOW_CASES=sandbox-selftest`, with `MADCOWORK_SELFTEST_URL` pointing
to the isolated backend URL and its token supplied through the environment.

### Git control data and macOS descendant cleanup (SBX-FIX)

For model and hook commands, `gitConfinementPolicy.mjs` derives the protected
paths for every provider. The entire `.git` tree is read-only, including linked
worktree pointers, common directories and submodule metadata. Git configuration
origins, recursive includes (including inactive conditional includes), custom
hook directories and attributes/modules files are protected too. Standard
global Git config and attributes names are reserved even when absent or empty.
The broker also collects `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG`
and `GIT_CONFIG_COUNT` key/value controls from its own environment and one
bounded `$SHELL -lc` environment probe. Include, hooksPath and attributes-file
values are resolved against each workspace and protected while absent. Only
policy-related variables are retained; shell output is never logged. A terminal
environment changed after this once-per-process probe is not known until restart.
Seatbelt also prevents renaming protected paths through an ancestor directory.
Writable symlink ancestors and hardlinked control data fail closed. Discovery
has finite budgets and fails closed if it cannot inspect the complete tree.
Linux reserves an absent root `.git` using an empty read-only directory mount;
bubblewrap can leave the empty mount-point directory on the host. It does not
turn a missing `.git` into an invalid pointer file. Seatbelt denies the
`.gitattributes` and `.gitmodules` names at every depth, including future
directories. Bubblewrap 0.12 places each workspace/grant in a per-execution
overlay, while Landlock uses the private copy stage described above, so no
untrusted write is host-visible while the command runs. After exit the shared
trusted publisher scans the merged/staged tree. A changed protected control
refuses the complete publication and returns a nonzero structured reason;
protected output is never silently omitted. A `.git` that did not exist before
execution is the narrow exception. The publisher rebuilds it from safe ordinary
files: `HEAD`; allowlisted `core`, `extensions`, `remote` and `branch` config
keys; `objects` except alternates/promisor/keep sidecars; `refs`, `packed-refs`, `index`, `logs`,
`shallow`, `info/exclude`, and `info/sparse-checkout`. Local remote URLs are
normalized relative to the published worktree. Hooks and unknown metadata are
discarded, hardlinks crossing the new repository boundary are rejected, internal
hardlinks are detached, and config is rewritten instead of copied. Before any
untrusted overlay or copy stage is created, the broker resolves Git to an absolute
real path, verifies its ownership and non-writable path chain, and rejects a
binary or helper directory below the workspace, a grant, temp, app-data, stage or
recovery root. The immutable publisher manifest carries that executable plus a
fixed `GIT_EXEC_PATH`; publisher and Git-policy discovery never resolve `git`
through ambient `PATH`. Trusted Git receives a minimal PATH containing only the
validated Git/toolchain and system directories. If that boundary cannot be
established, execution fails closed with a localized refusal before the model
command starts. Resolution is lazy: an ordinary non-repository workspace does
not require Git; existing Git metadata or a newly staged repository asks for it
only when publication needs inspection.

On Windows, native known-folder APIs supply the Windows and Program Files roots;
environment prefixes such as `SystemRoot` and `ProgramFiles` are never trust
anchors. A digest-verified bundled native helper opens the executable, helper
directory, every `git-*` helper and each ancestor without following reparse
points, then reads the owner and DACL from the handle. Only TrustedInstaller,
SYSTEM and Administrators are accepted owners. Any write grant to another SID,
a junction/reparse point, an unreadable descriptor or an indeterminate ACE
rejects the path. The same primitive selects `cmd.exe` and the system-Python
fallback and is required for future PowerShell, Node or Python system fallbacks.

This intentionally does not reproduce an interactive PATH. Homebrew SSH,
custom Git credential helpers and Git LFS/plugin helpers are not app-selected;
use them in a trusted terminal workflow. There is no ambient-PATH fallback when
a system or bundled tool cannot be proved safe.

Before the pinned Git runs, a no-follow traversal validates inode types; raw index, refs, pseudo-refs
and reflogs are parsed with finite limits. Every ref-reachable tree, including
packed refs, annotated tags and replace refs, is checked for unsafe paths, modes,
gitlinks, submodule metadata and executable attributes. Index-only
`.gitmodules` blobs are rejected even when the worktree file is absent. This supports
default-template, shallow, and sparse clones without
making a host executable path. New submodule and LFS metadata remain unsupported
in this release and produce localized host-side alternatives.
Existing `.git` trees remain immutable. Captured and detached commands therefore
close the read-before-restore window, while a validated new clone remains usable.
Host file watchers see changes only during the exit-time publish phase, not live;
publication is not one filesystem transaction. The helper first scans the complete merged tree, rejects
new/replaced special nodes, and enforces path/count/byte budgets before its first
host mutation. It compares regular-file content, not size/mtime metadata alone.
A validation failure changes no host file. Each destructive action records and
rechecks target identity, content and mode through pinned parent/target
descriptors. Existing values are quarantined and verified before a no-clobber
install, so a concurrent edit, create, delete, rename or symlink swap stops with
an explicit conflict instead of being overwritten. An I/O failure or a conflict
after an applied prefix returns partial status with the operation and prefix
count. The localized UI gives the full recovery-copy location and comparison
instructions. If the broker recovery directory is across a mount boundary, the
old inode is never copied and unlinked: its atomic quarantine pathname remains on
the target filesystem and the broker archive contains a manifest pointing to it.
Successful publications return that archive path as well. A detached
command publishes only when it exits, and a backend crash before publication can
leave changes only in the temporary overlay.

Before each bubblewrap execution the broker probes the actual workspace/grant
roots together with the real upper/work filesystem. The cache key includes those
root paths and filesystem device identities. If that mount fails, Landlock is
selected when its partial guarantees are available; otherwise the command is
refused before it starts with `SANDBOX_WORKSPACE_OVERLAY_UNAVAILABLE`. There is
no unconfined fallback. The general availability check intentionally does not
promise that every future NFS/FUSE/idmapped workspace supports overlay. If an
actual overlay probe fails, the Landlock fallback uses the same private
staging/publication path rather than writing to the workspace directly.

Changes to a repository that existed before the command, including `git add`,
`commit`, `checkout`, `config` and worktree metadata updates, are intentionally
refused at publication. A repository created entirely by the current command may
be published only after the narrow validation above. Use the existing file-scoped
Developer Mode `git_commit` tool for existing repositories. Host-side Developer Mode and CLI worktree
Git operations disable hooks, fsmonitor, configured filters, external diff,
text conversion, commit/tag signing and signature display/verification; the
fixed log/show calls also pass `--no-show-signature`. GPG, SSH-signature and
X.509 verifier programs are cleared, external protocols are denied, and global
attributes are ignored. This also prevents attributes from selecting an
executable driver. These tools produce raw file content;
projects requiring LFS/other filters or signed commits must use a trusted
terminal workflow. `.gitmodules` cannot itself define a shell update command,
and host worktree commands disable submodule recursion. Files-panel diffs use
checkpoint snapshots and do not invoke Git.

The publication path uses no external `cp`, `tar`, `rsync`, or shell. File
copying and archive retention use descriptor-based Node filesystem operations;
the finalizer launches the absolute Node executable, the preselected absolute
sandbox executable, and fixed `/bin/sh` (or `%SystemRoot%\\System32\\cmd.exe`
when an explicitly unconfined Windows shell is requested). User-requested
commands may still intentionally use their own PATH, but no broker finalizer or
publisher trusts it.

`process.execPath` is trusted only as an application-bootstrap premise. A signed
release launches Node/Electron from its signed bundle. A source or development
session deliberately started through an attacker-controlled PATH has already
lost that premise before this policy runs; the resolver does not claim to repair
a compromised parent process.

On Windows, a source/development launch may therefore report
`SANDBOX_TRUSTED_EXECUTABLE_UNAVAILABLE` even when a similarly named program is
on PATH: PATH and environment-derived installation prefixes are not trusted
system-tool sources. Use the packaged, signed application for the normal user
experience. Tests that must exercise this branch should use the explicit
trusted-executable test seam; development mode does not weaken the production
resolver or silently run the command without confinement. A refused HPC helper
similarly reports `TRUSTED_HPC_HELPER_REFUSED` when its interpreter or bundled
script closure cannot be verified.

Test runs use a fresh top-level temporary root and point `TMPDIR`, `TMP`, and
`TEMP` at it before Vitest workers start. Link cleanup is ownership-aware: a
test removes only links it registered or link identities (byte path plus
device/inode) added since that test's baseline, while suite-scoped and older
links remain untouched until their owner removes them. Code that captured an
`fs.symlink*` function reference before the setup interceptor was installed is
not assumed to be intercepted; the per-test no-follow identity difference and
the command-level run-root gate are a fallback only for links created inside
the private run root. Test launch hygiene has three layers:

1. The first Vitest setup wraps all seven public `child_process` launch APIs
   and `worker_threads.Worker`. A replacement environment receives missing
   `TMPDIR`, `TMP`, and `TEMP`; omitted Worker environments and `SHARE_ENV`
   keep normal inheritance. Environment copying deliberately uses `for...in`,
   matching Node's inclusion of inherited enumerable entries. On Windows the
   winning case-insensitive key is the first after lexicographic sorting, just
   as in Node; duplicate case aliases fail closed, and the winning value is the
   value checked against the run root. The three controlled keys are the only
   additions, so product environment-scrubbing assertions retain their meaning.
2. The run-root gate catches pre-bound filesystem calls and child/shell-created
   links only when the launch inherited or received the controlled temp and the
   link was actually created inside that root. Explicit outside-root temp
   values fail the command without scanning or cleaning shared host temp.
3. `audit:test-launch-surfaces`, also run by `npm test` before Vitest, covers
   the following explicit AST forms. Low-level receivers may be the global
   `process`, `globalThis.process`, or `global.process`, using dot or
   string-literal bracket notation. They may also be one same-file, single-hop,
   name-unique `const`/`let` alias initialized in its declaration or assigned
   once directly by a standalone statement at file or function-body level.
   Calls to `binding` and `_linkedBinding` are rejected through dot/literal
   bracket access, a `const`/`let` destructuring binding from one of those
   process expressions, and direct `.call`/`.apply`. Direct or global-object
   `internalBinding` calls are rejected. Parentheses, TypeScript `as`, non-null
   and `satisfies`, and direct `await` wrappers are unwrapped.

   Worker module specifiers may be either `node:worker_threads` or bare
   `worker_threads` in static ESM, dynamic `import()`, or CommonJS `require()`.
   The audit follows ESM named Worker bindings; default-import module objects;
   namespace `.Worker`, `.default.Worker`, and literal `['Worker']`; CJS
   destructuring, namespace, and direct Worker properties; and a simple
   constructor identifier alias. A direct options object, or a simple same-file
   options identifier, is rejected when it explicitly contains `env`, except
   inside the shared fixture Worker helper.

   Configured setup modules may not capture `spawn`, `spawnSync`, `exec`,
   `execSync`, `execFile`, `execFileSync`, or `fork`. Both
   `node:child_process` and bare `child_process` are recognized for static ESM
   named/default/namespace imports, dynamic `import()`, and CommonJS
   `require()`; destructuring, namespace/literal property access, direct
   properties, top-level identifier aliases, and stores on a
   `globalThis`/`global` property are rejected. Every `setupFiles` list must put
   hygiene first.

   Multiple or conditional process-alias assignments, non-standalone
   assignments, dynamically computed names, `eval`/generated code, reflection,
   multi-hop or cross-file process aliases, native add-ons, and arbitrary data
   flow are outside this audit and remain a code-review boundary; none is
   claimed as a runtime guarantee.

All test files in a run currently share that one private root, while ownership
baselines live in individual workers. `fileParallelism: false` is therefore a
correctness invariant, not a performance preference: parallel files could
mistake another worker's suite link for their own and unlink it. Global setup
refuses any configuration that enables file parallelism. Supporting it in a
future 0.68.x requires a separate private root per worker.

Links registered outside the private run root are never scanned or removed and
make the test command fail closed.

On macOS, build the native supervisor before standalone development/tests:
`node scripts/bundle-mac-supervisor.mjs`. The macOS packaging hooks build the
universal arm64/x86_64 binary and verify its presence after packing. Captured
sandbox executions fail closed if the helper is absent. Its directory is itself
write-protected. Every run carries a two-colour Seatbelt identity: one existing
marker is denied and a peer is explicitly allowed. The host supervisor enumerates
same-UID processes and uses `sandbox_check` to rediscover that identity after a
fast double-fork, setsid or reparenting without matching unrelated deny-by-default
App Sandboxes. Cleanup repeatedly freezes the set, then sends PID-version-bound
SIGKILL through audit tokens until it is empty. Captured and explicit detached
broker jobs both use the supervisor; detached mode keeps its documented survival
across backend restart. The Seatbelt child cannot signal the host supervisor or
apply a second sandbox profile to erase its identity. Host launch delegation is
closed separately: Seatbelt denies `lsopen`, Apple Events, launchd `job-creation`,
on-demand XPC lookups, and the LaunchServices/Quick Look/Spotlight bootstrap
names.

| Broker path | Boundary | Compatibility decision |
|---|---|---|
| LaunchServices, `open`, URL schemes and Terminal activation | `lsopen` plus LaunchServices bootstrap names denied | Direct `exec` remains available; a true `.app` host-positive/sandbox-negative regression is required |
| `launchctl submit/bootstrap/asuser` | `job-creation` denied | Ordinary fork/exec is unaffected |
| Apple Events, `osascript`, System Events | `appleevent-send` denied | GUI delegation is intentionally unavailable |
| On-demand XPC services | all `xpc-service-name` lookups denied | Node, Python, Git and npm command-line smoke tests must remain green |
| Quick Look and Spotlight request brokers | named bootstrap lookups plus job creation denied | Direct file search/inspection remains available; brokered previews/importers are intentionally unavailable |
| Login Items | Apple Events denied and BTM/SFL stores read-only | Registration is intentionally unavailable |
| `at`/cron and Launch Agents | scheduler/persistence files protected; launchd job creation denied | Existing scheduler inspection may work; creation does not |

P10 exercises timeout and
abort with detached grandchildren, and a native regression covers stale birth IDs
and pidversions. `processContainment` is derived from live P14 rather than assigned
unconditionally. With P1–P15 plus the LaunchServices regression passing, macOS
reports `processContainment=strong`
and meets its `strong` release expectation. This guarantee assumes the trusted
host does not externally SIGKILL or tamper with the supervisor itself. Linux bubblewrap
continues to use a PID namespace plus the inner Unix-socket guard; Landlock
relies on its syscall filters and subreaper cleanup and is reported as partial.

The login-shell environment probe uses the same native lifecycle mechanisms
without changing shell semantics: macOS runs an identity-marked Seatbelt child
under the native supervisor, while Linux uses helper 4 in supervisor-only mode
with `PR_SET_CHILD_SUBREAPER`. A deadline signals the trusted supervisor and
waits for its identity/subreaper cleanup, so an ignored SIGTERM, setsid or
double-fork descendant holding stdout/stderr cannot survive or keep the probe
open. The probe child cannot signal that supervisor (Seatbelt's sandbox
identity boundary on macOS, seccomp on Linux). Linux refuses the confined
command if the supervisor helper is absent.

Implementation references: [Git attributes](https://git-scm.com/docs/gitattributes),
[Git modules](https://git-scm.com/docs/gitmodules),
[Git hooks](https://git-scm.com/docs/githooks),
[Apple's audit-token signal implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/proc_info.c),
and the libSystem `sandbox_check` ABI.

### Backend selection and host-process checks (SBX-L-r2)

The broker selects one frozen, module-issued ticket containing a verified backend
and its executable. macOS Seatbelt, bundled/system bubblewrap and Landlock wrapping
consume that selection without another readiness probe or executable lookup.
A disappearing executable causes spawn failure. A provider returning
`usedSandbox:false` is rejected for `require`, and also for `prefer` without an
explicit unconfined allowance. A ticket pins a pathname, not an inode against a
concurrent trusted host administrator replacing the executable.

Helper version 2 rejects old version-1 artifacts. Linux health check P14 starts
its own disposable host victim outside the command sandbox, attempts `fcntl`
SIGIO delivery and `prlimit64` against it through the actual broker, and checks
both syscall refusal and unchanged victim state. Removing either filter makes
the Linux host-process regression fail. Runtime health P14 uses the shared
cross-platform disposable-victim probe and requires P1–P15 everywhere; old
fourteen-probe reports are insufficient. Landlock remains capped at **partial**,
including with fifteen passing checks.

The native syscall audit is for x86-64 and aarch64; compat/x32 is rejected before
these rules. Unknown future syscalls are not a promise of comprehensive isolation.

| Interface | Policy and reason |
|---|---|
| `fcntl` / `fcntl64` | Allow-list ordinary flags, dup, advisory locks, seals and pipe sizing. Refuse `F_SETOWN`, `F_SETOWN_EX`, `F_SETSIG`, `F_SETLEASE`, `F_NOTIFY` and unknown commands (including newer delegations). `F_SETFL` additionally refuses `O_ASYNC`; ordinary nonblocking/CLOEXEC flags work. |
| `prlimit64` | Only literal pid=0 (both argument halves zero), for self limits. Nonzero, including the caller's explicit PID, is refused. `getrlimit`/`setrlimit` affect only self. |
| `setpriority`, `sched_setaffinity`, `sched_setscheduler`, `sched_setparam`, `sched_setattr`, `ioprio_set` | Refused globally, including self variants; they can otherwise degrade same-UID host scheduling. This is a compatibility restriction. |
| `process_madvise`, `process_mrelease`, `migrate_pages`, `move_pages` | Refused; no remote memory reclamation, migration or advice. |
| `pidfd_open`, `pidfd_getfd`, `pidfd_send_signal` | Refused; no host process handles, descriptor borrowing or signals. |
| `ptrace`, `process_vm_readv`, `process_vm_writev`, `kcmp`, `get_robust_list`, `perf_event_open` | Refused; no inspection/control through tracing, memory, kernel pointer or performance interfaces. |
| `kill`, `tkill`, `tgkill`, `rt_sigqueueinfo`, `rt_tgsigqueueinfo` | Refused, including self signals; supervisor cleanup runs outside the filter. |
| `clone` / `clone3`, `setns`, `unshare` | No CLONE_PARENT or namespace creation; clone3 returns ENOSYS, namespace entry/creation is refused. A clone exit signal can target only its own parent/supervisor. |
| `setpgid`, `setsid` | Kernel restricts mutation to self/eligible children, never an unrelated process. Descendant reparenting/setsid is covered by the subreaper cleanup tests. |
| `wait4`, `waitid` | Kernel child relationship requirement prevents reaping unrelated host processes. No inheritable pidfds survive the descriptor gate. |
| `getpriority`, `ioprio_get`, `sched_get*`, `getpgid`, `getsid` | Read-only process metadata may remain visible; this backend has no PID namespace and does not claim metadata secrecy. |
| `prctl`, `set_tid_address`, `set_robust_list`, `rseq`, `sched_yield`, interval/POSIX timers | Self/thread-group operations; timer thread targeting is limited to the caller's thread group. They do not accept arbitrary unrelated host signal recipients. |
| `ioctl`, `io_uring`, IPC, `/proc` | Existing restrictive ioctl allow-list, io_uring/IPC denials, closed inherited fds and `/proc` denial prevent alternative descriptor/control paths. |

The tests attempt every added syscall against an owned unrelated victim and
verify signal count, limits, nice value, affinity, scheduler and I/O priority.
Unconfined controls are required to succeed for usable interfaces; permission- or
state-dependent calls retain their actual kernel error rather than claiming a
successful positive control. This is not resource-quota or denial-of-service
isolation; advisory locks and explicitly shared writable files still have ordinary
host semantics.

References: [Linux fcntl](https://man7.org/linux/man-pages/man2/fcntl.2.html),
[resource limits](https://man7.org/linux/man-pages/man2/getrlimit.2.html),
[kernel seccomp](https://docs.kernel.org/userspace-api/seccomp_filter.html),
[kernel Landlock limitations](https://docs.kernel.org/userspace-api/landlock.html).
