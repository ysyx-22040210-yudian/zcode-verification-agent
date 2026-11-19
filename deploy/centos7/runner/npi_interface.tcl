# Interface ports bind to elaborated objects. Use the formal's own statements for access direction.
namespace eval nq {
    proc isBundle {port} { return [expr {[prop $port npiPortType] in {npiModportPort npiInterfacePort}}] }
    proc binding {port} {
        set low [rel $port npiLowConn]
        set actual [rel [rel $port npiHighConn] npiActual]
        set view [rel $low npiActual]
        if {[kind $actual] eq "npiModport"} { set actual [rel $actual npiScope] }
        if {[kind $actual] ne "npiInterface"} { return {} }
        if {[kind $view] ne "npiModport"} { set view "" }
        return [list $actual $view $low]
    }
    proc formalBinding {path} {
        set dot [string last "." $path]
        if {$dot < 1} { return {} }
        set ownerPath [string range $path 0 $dot-1]
        set owner [npi_handle_by_name -name $ownerPath -scope ""]
        if {[kind $owner] ne "npiModule"} { return {} }
        if {[full $owner] ne $ownerPath} {
            set owner ""
            foreach m [modules] { if {[full $m] eq $ownerPath} { set owner $m; break } }
        }
        set portName [string range $path $dot+1 end]
        foreach p [items $owner npiPort] {
            if {[name $p] eq $portName && [isBundle $p]} { return [binding $p] }
        }
        return {}
    }
    proc dataMember {io} {
        set expr [rel $io npiExpr]
        if {[kind $expr] in {npiNet npiReg npiBitVar npiIntegerVar npiIntVar npiByteVar npiShortIntVar npiLongIntVar npiEnumVar npiStructVar}} {
            return [name $expr]
        }
        return ""
    }
    proc exposedMembers {view base physical bits} {
        if {$view eq ""} { return [list [list $base unrestricted]] }
        set found {}
        foreach io [items $view npiIODecl] {
            set target [dataMember $io]
            if {$target eq $base} {
                lappend found [list [name $io] [prop $io npiDirection]]
            } elseif {$target eq "" && [matches [rel $io npiExpr] [list $base $physical] $bits]} {
                warn "Compound modport expression for [name $io]; port-to-member bit mapping unavailable"
            }
        }
        return $found
    }
    proc selection {label} {
        if {[regexp {^(.+?)\[(-?[0-9]+)(?::(-?[0-9]+))?\]$} $label -> base a b]} {
            if {$b eq ""} { set b $a }
            return [list $base [expr {min($a,$b)}] [expr {max($a,$b)}]]
        }
        return [list $label]
    }
    proc matches {h aliases bits} {
        if {$h eq ""} { return 0 }
        if {[kind $h] eq "npiExtRef"} {
            set names [list [full [rel $h npiActual]]]
        } else {
            set names [list [name $h] [full $h]]
        }
        foreach candidate $names {
            set span [selection $candidate]
            set base [lindex $span 0]
            foreach alias $aliases {
                if {$base eq $alias} {
                    if {[llength $span] == 1 || [llength $bits] == 1 ||
                        ([lindex $span 1] <= [lindex $bits 2] && [lindex $bits 1] <= [lindex $span 2])} { return 1 }
                } elseif {[string first [format {%s[} $alias] $base] == 0} {
                    if {[llength $bits] > 1} { warn "Variable index on $alias; static bit overlap is undetermined" }
                    return 1
                }
            }
        }
        foreach op [items $h npiOperand] { if {[matches $op $aliases $bits]} { return 1 } }
        return 0
    }
    proc uses {obj aliases bits scope} {
        foreach u [items $obj npiUse] {
            set type [kind $u]
            if {$type in {npiMpPort npiMpPortBit npiModport}} { continue }
            set owner [full [rel $u npiScope]]
            if {$owner eq ""} { set owner $scope }
            set lhs [rel $u npiLhs]
            set rhs [rel $u npiRhs]
            if {$lhs ne "" || $rhs ne ""} {
                if {[matches $lhs $aliases $bits]} { endpoint driver $owner $u [list [display $rhs]] }
                if {[matches $rhs $aliases $bits]} { endpoint load $owner $u [list [display $lhs]] }
            } elseif {$type in {npiPort npiPortBit}} {
                if {[isBundle $u] || ![matches [rel $u npiHighConn] $aliases $bits]} { continue }
                set dir [prop $u npiDirection]
                if {$dir in {npiInput npiInout}} { endpoint load $owner $u [list [name $u]] }
                if {$dir in {npiOutput npiInout}} { endpoint driver $owner $u [list [name $u]] }
            } else {
                set cond [rel $u npiCondition]
                if {$cond eq ""} { condRead $u $owner $aliases $bits } elseif {[matches $cond $aliases $bits]} {
                    endpoint load $owner $u [list [display $cond]]
                }
            }
        }
    }
    proc condRead {u owner aliases bits} {
        foreach type {npiExpr npiCondition npiEventControl} {
            set expr [rel $u $type]
            if {$expr ne "" && [matches $expr $aliases $bits]} {
                endpoint load $owner $u [list [display $expr]]
                return
            }
        }
        warn "Unclassified [kind $u] use in $owner at [prop $u npiFile]:[line $u]"
    }
    proc interfaceSignal {path iface view member} {
        set bits [selection $member]
        set base [lindex $bits 0]
        if {$view ne ""} {
            set decl ""
            foreach io [items $view npiIODecl] { if {[name $io] eq $base} { set decl $io; break } }
            if {$decl eq ""} { return not_found }
            set target [dataMember $decl]
            if {$target eq ""} {
                warn "Compound modport expression for $base; query the physical interface member"
                return unsupported
            }
            set member "$target[string range $member [string length $base] end]"
            set base $target
            set bits [selection $member]
        }
        set canonical "[full $iface].$member"
        set h [npi_handle_by_name -name $canonical -scope ""]
        if {$h eq ""} { return not_found }
        if {[kind $h] in {npiModport npiInterface} || ![regexp {^npi(Net|Reg|.*Var|PartSelect|MemoryWord)} [kind $h]]} {
            warn "Select a static data member of the interface"
            return unsupported
        }
        emit signal $path $canonical [kind $h]
        # 接口成员的 L1 load 还会返回受条件控制的赋值。直接用 npiUse 定位实际读写该成员的语句。
        set sig [npi_handle_by_name -name $base -scope $iface]
        set physical "[full $iface].$base"
        uses $sig [list $physical] $bits [full $iface]
        foreach mod [modules] {
            foreach port [items $mod npiPort] {
                if {![isBundle $port]} { continue }
                lassign [binding $port] actual mp low
                if {$actual eq "" || [full $actual] ne [full $iface]} { continue }
                set owner [full $mod]
                set formal [name $port]
                foreach exposed [exposedMembers $mp $base $physical $bits] {
                    lassign $exposed visible direction
                    record binding [list $owner $formal [name $mp] $direction [full $iface]]
                    uses $low [list "$formal.$visible" "$owner.$formal.$visible" $physical] $bits $owner
                }
            }
        }
        return ok
    }
}

