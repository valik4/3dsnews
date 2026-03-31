package main

import (
	"flag"
	"fmt"
	"os/exec"
	"runtime"
)

// Args flags (force or disable)
var g_fl_dry, g_dfl_hb, g_dfl_rt, g_dfl_rw, g_ffl_rw, g_dfl_nt bool

func init() {
	flag.BoolVar(&g_fl_dry, "dry", false, "Dry run.")
	flag.BoolVar(&g_dfl_hb, "dhb", false, "Disable homebrew updates.")
	flag.BoolVar(&g_dfl_rt, "drt", false, "Disable rutracker updates.")
	flag.BoolVar(&g_ffl_rw, "frw", false, "Force retro weekend.")
	flag.BoolVar(&g_dfl_rw, "drw", false, "Disable retro weekend.")
	flag.BoolVar(&g_dfl_nt, "dnt", false, "Disable notification when finished.")
}

func main() {
	// Parsing provided arguments
	flag.Parse()
	hb_str := ""
	// Homebrew updates
	if !g_dfl_hb {
		hb_str = Homebrew_updates(g_fl_dry)
	}

	// Printing errors
	if err_ctr_hb > 0 {
		fmt.Println("Homebrew update errors: ")
		for ctr := range error_arr_hb {
			println(error_arr_hb[ctr])
		}
		println()
	}

	// Printing homebrew updates
	if len(hb_str) > 0 {
		fmt.Print(hb_str)
	}

	// OS based notification | go tool dist list - list all platforms
	if !g_dfl_nt {
		switch runtime.GOOS {
		case "darwin":
			exec.Command("osascript", "-e", `display notification "done" with title "hbnews"`).Run()
		case "linux":
			exec.Command("/usr/bin/notify-send", "-e", "-i", "noicon", "hbnews", "Finished").Run()
		}
	}
}
