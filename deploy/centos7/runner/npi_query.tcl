# Executed by Verdi batch. Only the launcher supplies Tcl scripts; query data travels as environment values.
namespace eval nq {
    proc prop {h key} {
        if {$h eq ""} { return "" }
        return [npi_get_str -property $key -object $h]
    }
    proc rel {h type} {
        if {$h eq ""} { return "" }
        return [npi_handle -type $type -refHandle $h]
    }
    proc items {h type} {
        set out {}
        if {$h eq ""} { return $out }
        set it [npi_iterate -type $type -refHandle $h]
        if {$it ne ""} {
            while {[set obj [npi_scan -iterator $it]] ne ""} { lappend out $obj }
        }
        return $out
    }
    proc full {h} { return [prop $h npiFullName] }
    proc kind {h} { return [prop $h npiType] }
    proc name {h} { return [prop $h npiName] }
    proc line {h {key npiLineNo}} {
        if {$h eq ""} { return 0 }
        set n [npi_get -property $key -object $h]
        if {![string is integer -strict $n] || $n < 0} { return 0 }
        return $n
    }
    proc display {h} {
        if {$h eq ""} { return "" }
        set s [full $h]
        if {$s eq ""} { set s [name $h] }
        if {$s eq ""} { catch {set s [::npi_L1::npi_expr_decompile $h]} }
        return [string range $s 0 1023]
    }
    proc emit {tag args} {
        variable stream
        set row [list $tag]
        foreach field $args {
            binary scan [encoding convertto utf-8 $field] H* encoded
            lappend row $encoded
        }
        puts $stream [join $row "\t"]
    }
    proc record {tag fields} {
        variable seen
        variable counts
        set key [list $tag $fields]
        if {[info exists seen($key)]} { return }
        set seen($key) 1
        incr counts($tag)
        if {$counts($tag) > $::env(NQ_LIMIT)} { return }
        if {$tag in {driver load} && [llength $fields] > 13} {
            warn "Related signals limited to eight per endpoint; endpoint totals are preserved"
            set fields [lrange $fields 0 12]
        }
        emit $tag {*}$fields
    }
    proc warn {message} { record warning [list $message] }
    proc requested {direction} {
        return [expr {$::env(NQ_DIRECTION) eq "both" || $::env(NQ_DIRECTION) eq $direction}]
    }
    proc endpoint {direction scope use related} {
        if {![requested $direction]} { return }
        record $direction [list $scope [kind $use] [prop $use npiFile] [line $use] [name $use] {*}$related]
    }
    proc modules {} {
        variable mods
        if {![info exists mods]} {
            set mods {}
            ::npi_L1::npi_find_inst_with_def_wildcard "" {*} mods
        }
        return $mods
    }
    proc globmatch {pattern text} {
        # Keep SV array and generate indices literal. Only star and question mark are wildcards.
        return [string match [string map [list "\\" "\\\\" "\[" "\\\[" "\]" "\\\]"] $pattern] $text]
    }
    proc instances {} {
        set scope $::env(NQ_SCOPE)
        foreach h [modules] {
            if {[kind $h] ne "npiModule"} { continue }
            set path [full $h]
            if {$scope ne "" && $path ne $scope && [string first "$scope." $path] != 0} { continue }
            set def [prop $h npiDefName]
            if {[globmatch $::env(NQ_DEFINITION) $def] && [globmatch $::env(NQ_INSTANCE) $path]} {
                record instance [list $path $def [prop $h npiFile] [line $h] [prop $h npiDefFile] [line $h npiDefLineNo]]
            }
        }
        variable counts
        if {$counts(instance) == 0} { return no_matches }
        return ok
    }
    proc ordinary {h} {
        foreach direction {driver load} {
            if {![requested $direction]} { continue }
            set rows {}
            set trace [format "::npi_L1::npi_trace_%s_by_hdl2" $direction]
            set rc [$trace $h rows 1]
            if {$rc != 0} { warn "NPI $direction trace returned $rc" }
            foreach row $rows {
                lassign $row origin scope pass uses use signals
                if {[kind $use] in {npiMpPort npiMpPortBit}} { continue }
                set other {}
                foreach s $signals {
                    set label [display $s]
                    if {$label ne ""} { lappend other $label }
                }
                endpoint $direction [full $scope] $use $other
            }
        }
    }
    proc signal {} {
        set path $::env(NQ_SIGNAL)
        set h [npi_handle_by_name -name $path -scope ""]
        set prefix [join [lrange [split $path .] 0 end-1] .]
        set member [lindex [split $path .] end]
        set owner [npi_handle_by_name -name $prefix -scope ""]
        set view ""
        if {[kind $owner] eq "npiInterface"} {
            set iface $owner
        } elseif {[kind $owner] eq "npiModport"} {
            set iface [rel $owner npiScope]
            set view $owner
        } else {
            lassign [formalBinding $prefix] iface view
        }
        if {$iface ne ""} {
            return [interfaceSignal $path $iface $view $member]
        }
        if {$h eq ""} { return not_found }
        if {[kind $h] in {npiInterface npiModport} || [lindex [formalBinding $path] 0] ne ""} {
            warn "Select a member of the interface or modport"
            return unsupported
        }
        if {![regexp {^npi(Net|Reg|Port|IntegerVar|TimeVar|BitVar|LogicVar|IntVar|ByteVar|ShortIntVar|LongIntVar|PartSelect|VarSelect|MemoryWord|StructVar|EnumVar)} [kind $h]]} {
            warn "Unsupported static object type: [kind $h]"
            return unsupported
        }
        emit signal $path [full $h] [kind $h]
        ordinary $h
        return ok
    }
    proc main {} {
        variable counts
        array set counts {instance 0 driver 0 load 0 binding 0 warning 0}
        uplevel #0 [list source [file join $::env(VERDI_HOME) share NPI L1 TCL npi_L1.tcl]]
        schSetPreference -detailRTL on -detailMux on -expandGenBlock on
        puts "NPI KDB: $::env(NQ_KDB)"
        if {[debImport -elab $::env(NQ_KDB)] != 1} { error "Verdi could not load the elaborated KDB: $::env(NQ_KDB)" }
        if {$::env(NQ_OPERATION) eq "instances"} { set outcome [instances] } else { set outcome [signal] }
        if {$outcome eq "ok" && $counts(warning) > 0} { set outcome partial }
        emit totals $counts(instance) $counts(driver) $counts(load) $counts(binding) $counts(warning)
        emit outcome $outcome
    }
}
set nq::stream [open $::env(NQ_OUTPUT) w]
if {[catch {
    source [file join $::env(NQ_RUNNER) npi_interface.tcl]
    nq::main
} err]} {
    nq::emit error $err
    puts stderr $::errorInfo
}
nq::emit end
close $nq::stream
debExit

