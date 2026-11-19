# Verdi NPI coverage extraction. A row is emitted while its native handle is valid.
encoding system utf-8
namespace eval cv {
    variable sequence 0
    variable view ""
    variable test ""
    variable sink
    proc emit {tag args} {
        variable sink
        set row [list $tag]
        foreach field $args {
            binary scan [encoding convertto utf-8 $field] H* hex
            lappend row $hex
        }
        puts $sink [join $row "\t"]
    }
    proc iterate {h relation parent metric scope {testArg 0}} {
        variable test
        if {$testArg} {
            set it [npi_cov_iter_start -type npiCov$relation -ref $h -test $test]
        } else {
            set it [npi_cov_iter_start -type npiCov$relation -ref $h]
        }
        if {$it eq ""} {return}
        # NPI automatically releases an exhausted iterator.
        while {[set obj [npi_cov_iter_next -iter $it]] ne ""} {
            visit $obj $parent $metric [string tolower $relation] $scope
            npi_cov_release_handle -ref $obj
        }
    }
    proc metricHandle {owner type metric parent scope} {
        set h [npi_cov_handle -type npiCov${type}Metric -ref $owner]
        if {$h ne ""} {
            visit $h $parent $metric metric $scope
            npi_cov_release_handle -ref $h
        }
    }
    proc visit {h parent metric relation prefix} {
        variable sequence
        variable view
        variable test
        set id [incr sequence]
        set raw [npi_cov_get_str -type npiCovType -ref $h]
        if {![string match npiCov* $raw]} {error "Unrecognized coverage object: $raw"}
        set kind [string range $raw 6 end]
        set name [npi_cov_get_str -type npiCovName -ref $h]
        set label $name
        if {[string match *Metric $kind]} {set label $metric}
        if {$kind eq "CoveredTest"} {set label [file tail $name]}
        set scope "$prefix/$label"
        set props {}
        foreach {key attr} {fullName FullName definition DefName file FileName valueText Value toggleType ToggleType} {
            set x [npi_cov_get_str -type npiCov$attr -ref $h]
            if {$x ne ""} {lappend props $key $x}
        }
        set ints {typeCode Type line LineNo size Size coverable Coverable value Value toggleCode ToggleType perInstance PerInstance isMda IsMda isPort IsPort isEventCondition IsEventCondition severity Severity category Category goal CountGoal}
        lappend ints status Status
        if {$test ne ""} {lappend ints covered Covered count Count}
        foreach {key attr} $ints {
            set x [npi_cov_get -type npiCov$attr -ref $h -test $test]
            if {$x ne "-1" && $x ne ""} {lappend props $key $x}
        }
        emit row $id $parent $view $metric $relation $kind $name $scope {*}$props
        if {$relation eq "component" || $kind eq "CoveredTest"} {return}
        if {$kind eq "Instance"} {
            foreach {type key} {Line line Condition condition Branch branch Toggle toggle Fsm fsm Assert assertion Testbench functional} {
                metricHandle $h $type $key $id $scope
            }
            iterate $h Instance $id hierarchy $scope
            return
        }
        iterate $h Child $id $metric $scope
        switch -- $kind {
            Covergroup {iterate $h CoverInstance $id $metric $scope}
            Cross {iterate $h Component $id $metric $scope}
            ConditionBin {iterate $h ConditionTerm $id $metric $scope}
            BranchBin {iterate $h BranchTerm $id $metric $scope}
            PowerDomain - PowerMeasure {iterate $h PowerData $id $metric $scope}
        }
        if {$test ne "" && [string match *Bin $kind]} {
            iterate $h CoveredTest $id $metric $scope 1
        }
    }
    proc collect {db h key label} {
        variable view $key
        variable test $h
        if {$h eq ""} {
            emit view $key $label "" ""
        } else {
            emit view $key $label [npi_cov_get_str -type npiCovType -ref $h] [npi_cov_get -type npiCovType -ref $h -test ""]
        }
        if {$h ne "" && $::env(CV_EXCLUDE) ne ""} {
            if {![npi_cov_load_exclude_file -test $h -file $::env(CV_EXCLUDE)]} {
                error "NPI could not apply the exclusion file"
            }
        }
        iterate $db Instance 0 hierarchy ""
        if {$h ne ""} {
            metricHandle $h Testbench functional 0 ""
            iterate $h PowerData 0 power ""
            if {$::env(CV_EXCLUDE) ne ""} {npi_cov_unload_exclusion -test $h}
        }
    }
    proc testsOf {db} {
        set tests {}
        set it [npi_cov_iter_start -type npiCovTest -ref $db]
        if {$it ne ""} {
            while {[set t [npi_cov_iter_next -iter $it]] ne ""} {lappend tests $t}
        }
        return $tests
    }
    proc openDb {} {
        set db [npi_cov_open -dir $::env(CV_DB)]
        if {$db eq "" || $db eq "0"} {error "NPI could not open the VCS coverage database"}
        return $db
    }
    proc extract {} {
        set db [openDb]
        emit database [npi_cov_get_str -type npiCovName -ref $db] [npi_cov_get_str -type npiCovType -ref $db] [npi_cov_get -type npiCovType -ref $db -test ""]
        set tests [testsOf $db]
        if {![llength $tests]} {collect $db "" design "Design shape"}
        set i 0
        foreach t $tests {
            collect $db $t test-[incr i] [npi_cov_get_str -type npiCovName -ref $t]
        }
        if {[llength $tests] > 1} {
            # 2018 版本在逐测试遍历后合并会使功能覆盖句柄失效。重新打开同一只读库再取句柄。
            npi_cov_close -db $db
            set db [openDb]
            set tests [testsOf $db]
            set merged [lindex $tests 0]
            foreach t [lrange $tests 1 end] {
                set merged [npi_cov_merge_test -dest $merged -src $t]
                if {$merged eq ""} {error "NPI could not merge the tests"}
            }
            collect $db $merged merged "Merged"
        }
        npi_cov_close -db $db
        emit end $::cv::sequence
    }
}
set cv::sink [open $::env(NQ_OUTPUT) w]
fconfigure $cv::sink -encoding ascii -translation lf
if {[catch cv::extract why]} {cv::emit error $why; puts stderr $::errorInfo}
close $cv::sink
debExit

