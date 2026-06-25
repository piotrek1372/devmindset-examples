#!/usr/bin/env gawk
# nginx combined log parser — summary report.
# Article: https://devmindset.dev/en/awk-as-a-full-programming-language-not-just-print-2/
# Usage: gawk -f log_parser.awk /var/log/nginx/access.log
#        zcat access.log.gz | gawk -f log_parser.awk
#
# nginx combined format:
#   addr - user [time] "request" status bytes "referer" "agent"

BEGIN { FS = " " }

NF < 9 { next }

{
    ip     = $1
    status = $9
    bytes  = ($10 ~ /^[0-9]+$/) ? $10 + 0 : 0
    method = substr($6, 2)    # "GET => GET (strip leading quote)
    path   = $7
    total++
    total_bytes += bytes
    ip_count[ip]++
    status_count[status]++
    if (status+0 >= 400) errors++
    split($4, ts, ":")        # [DD/Mon/YYYY:HH:MM:SS
    hour_count[ts[2]]++
}

END {
    if (!total) { print "no valid log lines" > "/dev/stderr"; exit 1 }

    printf "\n=== nginx report: %d requests ===\n", total
    printf "total bytes : %.2f MB\n", total_bytes/1024/1024
    printf "error rate  : %.1f%%  (%d errors)\n\n", errors/total*100, errors+0

    print "HTTP status distribution:"
    PROCINFO["sorted_in"] = "@ind_num_asc"
    for (s in status_count)
        printf "  %s  %5d  %.1f%%\n", s, status_count[s], status_count[s]/total*100

    printf "\nTop 10 IPs:\n"
    PROCINFO["sorted_in"] = "@val_num_desc"
    i = 0
    for (ip in ip_count) {
        if (++i > 10) break
        printf "  %-20s %d\n", ip, ip_count[ip]
    }

    printf "\nRequests per hour:\n"
    for (h = 0; h <= 23; h++) {
        n   = hour_count[sprintf("%02d", h)]+0
        bar = sprintf("%*s", int(n/total*50), "")
        gsub(/ /, "#", bar)
        printf "  %02d:xx  %-50s %d\n", h, bar, n
    }
}
