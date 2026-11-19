# Run by Verdi in a separate native process. User-provided names and paths are data.
# Verdi 2018 Tcl defaults to Latin-1 even on this UTF-8 host.
encoding system utf-8
namespace eval wave {
    proc emit {tag args} {
        variable output
        set row [list $tag]
        foreach value $args {
            binary scan [encoding convertto utf-8 $value] H* hex
            lappend row $hex
        }
        puts $output [join $row "\t"]
    }
    proc property {h p} { return [npi_fsdb_sig_property -sig $h -type $p] }
    proc fullname {h} { return [npi_fsdb_sig_property_str -sig $h -type npiFsdbSigFullName] }
    proc formatOf {h} {
        if {[property $h npiFsdbSigIsReal]} { return real }
        if {[property $h npiFsdbSigIsString]} { return string }
        return digital
    }
    proc value {v type} {
        set formats [dict create digital npiFsdbBinStrVal real npiFsdbRealVal string npiFsdbStringVal]
        set data [npi_fsdb_vct_value -vct $v -format [dict get $formats $type]]
        if {$type eq "digital"} { return [string tolower $data] }
        return $data
    }
    proc visitSignals {iter} {
        variable matched
        variable clipped
        variable glob
        if {$iter eq ""} { return }
        while {!$clipped && [set h [npi_fsdb_iter_sig_next -iter $iter]] ne ""} {
            set name [fullname $h]
            if {[string match -nocase $glob $name]} {
                if {$matched >= $::env(FW_LIMIT)} { set clipped 1; break }
                incr matched
                emit signal $name [property $h npiFsdbSigRangeSize] [formatOf $h]
            }
            if {[property $h npiFsdbSigHasMember]} { visitSignals [npi_fsdb_iter_member -sig $h] }
        }
        npi_fsdb_iter_sig_stop -iter $iter
    }
    proc visitScopes {iter} {
        variable clipped
        if {$iter eq ""} { return }
        while {!$clipped && [set scope [npi_fsdb_iter_scope_next -iter $iter]] ne ""} {
            visitSignals [npi_fsdb_iter_sig -scope $scope]
            if {!$clipped} { visitScopes [npi_fsdb_iter_child_scope -scope $scope] }
        }
        npi_fsdb_iter_scope_stop -iter $iter
    }
    proc catalog {file} {
        variable matched 0
        variable clipped 0
        variable glob
        set pattern $::env(FW_PATTERN)
        set glob [string map [list "\\" "\\\\" "\[" "\\\[" "\]" "\\\]"] $pattern]
        if {[string first "*" $glob] < 0 && [string first "?" $glob] < 0} { set glob "*$glob*" }
        visitSignals [npi_fsdb_iter_top_sig -file $file]
        if {!$clipped} { visitScopes [npi_fsdb_iter_top_scope -file $file] }
        emit catalog $clipped
        if {$matched == 0} { return no_matches }
        return ok
    }
    proc findTrigger {file from} {
        variable minTime
        variable maxTime
        set h [npi_fsdb_sig_by_name -file $file -scope "" -name $::env(FW_TRIGGER)]
        if {$h eq ""} { error "Trigger signal not found: $::env(FW_TRIGGER)" }
        set edge $::env(FW_EDGE)
        set type [formatOf $h]
        if {$edge ne "change" && ($type ne "digital" || [property $h npiFsdbSigRangeSize] != 1)} {
            error "Rising and falling triggers require a one-bit digital signal"
        }
        if {$from > $maxTime} { return [list no_trigger ""] }
        set v [npi_fsdb_create_vct -sig $h]
        if {$v eq ""} { return [list no_trigger ""] }
        set answer [list no_trigger ""]
        if {[npi_fsdb_goto_first -vct $v]} {
            set first [npi_fsdb_vct_time -vct $v]
            # 从前一 tick 的最后记录开始，保留 from 时刻的第一条实际边沿。
            if {$from > $first} { npi_fsdb_goto_time -vct $v -time [expr {$from - 1}] }
            set prev [value $v $type]
            set inspected 0
            while {[npi_fsdb_goto_next -vct $v]} {
                set t [npi_fsdb_vct_time -vct $v]
                set next [value $v $type]
                if {$t >= $from && (($edge eq "change" && $prev ne $next) ||
                    ($edge eq "rising" && $prev eq "0" && $next eq "1") ||
                    ($edge eq "falling" && $prev eq "1" && $next eq "0"))} {
                    set answer [list ok $t]; break
                }
                set prev $next
                if {[incr inspected] >= 1000000} { set answer [list trigger_limit $t]; break }
            }
        }
        npi_fsdb_release_vct -vct $v
        return $answer
    }
    proc readSignal {file name start end} {
        variable bytesLeft
        set h [npi_fsdb_sig_by_name -file $file -scope "" -name $name]
        if {$h eq ""} { emit lane $name 0 digital missing; return }
        set type [formatOf $h]
        set width [property $h npiFsdbSigRangeSize]
        if {$type eq "digital" && $width > 32768} { emit lane $name $width $type too_wide; return }
        set v [npi_fsdb_create_vct -sig $h]
        if {$v eq ""} { emit lane $name $width $type unavailable; return }
        if {![npi_fsdb_goto_first -vct $v]} {
            emit lane $name $width $type unavailable
            npi_fsdb_release_vct -vct $v
            return
        }
        set first [npi_fsdb_vct_time -vct $v]
        set initialPresent [expr {$first <= $start}]
        set initial ""
        if {$initialPresent} {
            if {![npi_fsdb_goto_time -vct $v -time $start]} { error "Cannot locate $name at $start" }
            set initial [value $v $type]
            if {[string bytelength $initial] > 32768} {
                emit lane $name $width $type too_wide
                npi_fsdb_release_vct -vct $v
                return
            }
        }
        emit lane $name $width $type ok $initialPresent $initial
        set has [expr {!$initialPresent || [npi_fsdb_goto_next -vct $v]}]
        set n 0
        while {$has} {
            set t [npi_fsdb_vct_time -vct $v]
            if {$t > $end} break
            if {$n >= $::env(FW_MAX_CHANGES) || $bytesLeft <= 0} { emit omitted $t; break }
            set val [value $v $type]
            set cost [expr {48 + [string bytelength $val]}]
            if {$cost > $bytesLeft || [string bytelength $val] > 32768} { emit omitted $t; break }
            emit change $t $val
            incr bytesLeft -$cost
            incr n
            set has [npi_fsdb_goto_next -vct $v]
        }
        npi_fsdb_release_vct -vct $v
    }
    proc traces {file} {
        variable minTime
        variable maxTime
        variable bytesLeft 524288
        set start $minTime
        set end $maxTime
        if {$::env(FW_START) ne ""} { set start $::env(FW_START) }
        if {$::env(FW_END) ne ""} { set end $::env(FW_END) }
        if {$::env(FW_TRIGGER) ne ""} {
            lassign [findTrigger $file $::env(FW_FROM)] status t
            emit trigger $status $t
            if {$status ne "ok"} {return $status}
            set start [expr {$t - $::env(FW_BEFORE)}]
            set end [expr {$t + $::env(FW_AFTER)}]
        }
        if {$end < $minTime || $start > $maxTime || $start > $end} { return outside_range }
        set start [expr {max($start, $minTime)}]
        set end [expr {min($end, $maxTime)}]
        emit window $start $end
        for {set i 0} {$i < $::env(FW_COUNT)} {incr i} {
            readSignal $file $::env(FW_SIG_$i) $start $end
        }
        return ok
    }
    proc run {} {
        variable minTime
        variable maxTime
        set f [npi_fsdb_open -name $::env(FW_FILE)]
        if {$f eq "" || $f eq "0"} { error "NPI could not open the FSDB file" }
        set minTime [npi_fsdb_min_time -file $f]
        set maxTime [npi_fsdb_max_time -file $f]
        emit file $minTime $maxTime [npi_fsdb_file_property_str -file $f -type npiFsdbFileScaleUnit]
        if {$::env(FW_OP) eq "signals"} { set outcome [catalog $f] } else { set outcome [traces $f] }
        emit outcome $outcome
        npi_fsdb_close -file $f
    }
}
set wave::output [open $::env(NQ_OUTPUT) w]
if {[catch wave::run message]} {
    wave::emit error $message
    puts stderr $::errorInfo
}
wave::emit end
close $wave::output
debExit

