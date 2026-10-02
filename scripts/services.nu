#!/usr/bin/env nu
# Manage the surrealmem API and worker as systemd user units.
#
#   nu scripts/services.nu install [--dry-run]   # render templates, install, enable --now
#   nu scripts/services.nu status
#   nu scripts/services.nu stop
#   nu scripts/services.nu logs <api|worker>

const repo = (path self | path dirname | path dirname)

def units []: nothing -> list<string> { ["surrealmem-api", "surrealmem-worker"] }

def api-port []: nothing -> int {
    let env_file = ($repo | path join .env)
    if not ($env_file | path exists) { return 8790 }
    let lines = (open --raw $env_file | lines | where { |l| $l | str starts-with "SURREALMEM_API_PORT=" })
    if ($lines | is-empty) { 8790 } else { $lines | first | str replace "SURREALMEM_API_PORT=" "" | str trim | into int }
}

def config []: nothing -> record {
    {
        REPO: $repo,
        UV: (which uv | get 0.path),
        API_PORT: (api-port | into string),
    }
}

def render [template: string, cfg: record]: nothing -> string {
    $cfg | columns | reduce --fold (open --raw $template) { |key, text|
        $text | str replace --all $"{{($key)}}" ($cfg | get $key)
    }
}

def "main install" [--dry-run]: nothing -> nothing {
    let cfg = (config)
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
    ^systemctl --user daemon-reload
    ^systemctl --user enable --now ...(units | each { |u| $"($u).service" })
    ^curl -fsS --retry 60 --retry-delay 2 --retry-connrefused --retry-all-errors $"http://127.0.0.1:($cfg.API_PORT)/health/ready" | ignore
    print "ready    surrealmem-api"
    print "started  surrealmem-worker"
}

def "main status" []: nothing -> table {
    let cfg = (config)
    units | each { |unit|
        { unit: $unit, active: (^systemctl --user is-active $"($unit).service" | complete | get stdout | str trim) }
    } | append {
        unit: "api health",
        active: (
            let probe = (do { ^curl -fsS --max-time 3 $"http://127.0.0.1:($cfg.API_PORT)/health/ready" } | complete);
            if $probe.exit_code == 0 { $probe.stdout | str trim } else { "unreachable" }
        )
    }
}

def "main stop" []: nothing -> nothing {
    ^systemctl --user disable --now ...(units | each { |u| $"($u).service" })
}

def "main logs" [which: string = "worker", --lines (-n): int = 50]: nothing -> nothing {
    ^journalctl --user -u $"surrealmem-($which).service" -n $lines --no-pager
}

def main []: nothing -> nothing {
    print "usage: nu scripts/services.nu <install [--dry-run]|status|stop|logs [api|worker]>"
}
