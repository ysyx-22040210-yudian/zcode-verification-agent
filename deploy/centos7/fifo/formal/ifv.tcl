clock -add clk -initial 0
force rst_n 0
run 2
init -load -current
constraint -add -pin rst_n 1
prove
assertion -show -all
catch {debug fifo_formal.p_simultaneous_hold -sstexport counterexample -overwrite}
exit
