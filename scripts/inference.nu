#!/usr/bin/env nu
# Manage the surrealmem inference units (llama-server for the instruct and embedding models).
#
#   nu scripts/inference.nu models            # download GGUFs (idempotent)
#   nu scripts/inference.nu install           # render unit templates, install, enable --now, wait for health
#   nu scripts/inference.nu install --dry-run # print the rendered units only
#   nu scripts/inference.nu status            # unit state + health endpoints
#   nu scripts/inference.nu stop              # stop and disable both units

const repo = (path self | path dirname | path dirname)

def load-env-file [file: string]: nothing -> record {
    if not ($file | path exists) { return {} }
    open --raw $file
    | lines
    | where { |l| ($l | str trim | str length) > 0 and not ($l | str trim | str starts-with "#") }
    | parse "{key}={value}"
    | reduce --fold {} { |row, acc|
        $acc | upsert $row.key ($row.value | str replace --all '$HOME' $env.HOME)
    }
}

def config []: nothing -> record {
    let base = (load-env-file ($repo | path join ops inference.env))
    let local = (load-env-file ($repo | path join ops inference.local.env))
    $base | merge $local | merge { REPO: $repo }
}

def render [template: string, cfg: record]: nothing -> string {
    $cfg | columns | reduce --fold (open --raw $template) { |key, text|
        $text | str replace --all $"{{($key)}}" ($cfg | get $key)
    }
}

def units []: nothing -> list<string> { ["surrealmem-llm", "surrealmem-embed"] }

def health-url [cfg: record, unit: string]: nothing -> string {
    if $unit == "surrealmem-llm" { $"http://127.0.0.1:($cfg.LLM_PORT)/health" } else { $"http://127.0.0.1:($cfg.EMBED_PORT)/health" }
}

# Download the GGUF models into MODELS_DIR.
def "main models" []: nothing -> nothing {
    let cfg = (config)
    mkdir $cfg.MODELS_DIR
    for m in [[repo file]; [$cfg.EMBED_REPO $cfg.EMBED_FILE] [$cfg.LLM_REPO $cfg.LLM_FILE]] {
        let target = ($cfg.MODELS_DIR | path join $m.file)
        if ($target | path exists) {
            print $"present  ($m.file) (ls $target | get 0.size)"
        } else {
            print $"download ($m.repo) ($m.file)"
            ^hf download $m.repo $m.file --local-dir $cfg.MODELS_DIR
        }
    }
}

# Render, install and start the units (or just print them with --dry-run).
def "main install" [--dry-run]: nothing -> nothing {
    let cfg = (config)
    if not ($cfg.LLAMA_SERVER | path exists) { error make { msg: $"llama-server not found at ($cfg.LLAMA_SERVER); set LLAMA_SERVER in ops/inference.local.env" } }
    let unit_dir = ($env.HOME | path join .config systemd user)
    for unit in (units) {
        let rendered = (render ($repo | path join ops systemd $"($unit).service.tmpl") $cfg)
        if $dry_run {
            print $"# ---- ($unit).service"
            print $rendered
        } else {
            mkdir $unit_dir
            $rendered | save --force ($unit_dir | path join $"($unit).service")
        }
    }
    if $dry_run { return }
    for m in [$cfg.LLM_FILE $cfg.EMBED_FILE] {
        if not (($cfg.MODELS_DIR | path join $m) | path exists) { error make { msg: $"model missing: ($m); run `just models` first" } }
    }
    ^systemctl --user daemon-reload
    ^systemctl --user enable --now ...(units | each { |u| $"($u).service" })
    for unit in (units) {
        let url = (health-url $cfg $unit)
        print $"waiting for ($unit) at ($url)"
        ^curl -fsS --retry 120 --retry-delay 2 --retry-connrefused --retry-all-errors $url | ignore
        print $"ready    ($unit)"
    }
}

# Show unit state and health.
def "main status" []: nothing -> table {
    let cfg = (config)
    units | each { |unit|
        let active = (^systemctl --user is-active $"($unit).service" | complete | get stdout | str trim)
        let health = (do { ^curl -fsS --max-time 3 (health-url $cfg $unit) } | complete)
        { unit: $unit, active: $active, health: (if $health.exit_code == 0 { $health.stdout | str trim } else { "unreachable" }) }
    }
}

# Stop and disable both units.
def "main stop" []: nothing -> nothing {
    ^systemctl --user disable --now ...(units | each { |u| $"($u).service" })
}

def main []: nothing -> nothing {
    print "usage: nu scripts/inference.nu <models|install [--dry-run]|status|stop>"
}
