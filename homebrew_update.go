package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os" // Цей пакет дозволяє працювати зі змінними оточення
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Settings
var hb_list = "list_hb.json"
var hist_fl_hb = "hist_hb.txt"
var hash_tag_hb = "\n#оновлення_софту:"

// Тепер ми не пишемо токени прямо в коді.
// Функція os.Getenv шукає змінну в системі. 
// Якщо її немає, вона просто поверне порожній рядок.
var github_token = "token " + os.Getenv("GITHUB_TOKEN")
var gitlab_token = os.Getenv("GITLAB_TOKEN")

type lab_release_entry struct {
	Tag_name string `json:"tag_name"`
	Date     string `json:"released_at"`
	Links    struct {
		Release_URL string `json:"self"`
	} `json:"_links"`
}

type hub_rel_entry struct {
	Html_url string `json:"html_url"`
	Tag_name string `json:"tag_name"`
	Date     string `json:"published_at"`
	Message  string `json:"message"`
	Assets   []struct {
		Updated string `json:"updated_at"`
	} `json:"assets"`
}

type HB_Entry struct {
	Category    string `json:"category"`
	App_name    string `json:"app_name"`
	API_url     string `json:"api_url"`
	HTML_url    string `json:"html_url"`
	Commit_date string `json:"comm_date"`
	Tag_name    string `json:"tag_name"`
	Description string `json:"description"`
	Prefix      string `json:"prefix"`
}

var error_arr_hb []string
var err_ctr_hb = 0

// Global counters
var hub_req_used, lab_req_used int = 0, 0
var t1_ctr, t2_ctr, t3_ctr, t4_ctr, t5_ctr, t6_ctr, t1_ttl, t2_ttl, t3_ttl, t4_ttl, t5_ttl, t6_ttl int = 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
var updates_ctr = 0


func lab_request(url string, req_num *int) []byte {
	client := &http.Client{}
	for {
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[lab_request] failed to create request: "+err.Error())
			err_ctr_hb++
			return nil
		}
		// No auth, so 60 requests per minute. Personal access token gives 600 requests
		if gitlab_token != "" {
			req.Header.Add("Private-Token", gitlab_token)
			//req.Header.Add("Authorization", "Bearer "+gitlab_token)
			req.Header.Add("Content-Type", "application/json")
		}
		resp, err := client.Do(req)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[lab_request] failed to perform request: "+err.Error())
			err_ctr_hb++
			return nil
		}
		defer resp.Body.Close()
		// Read ratelimits from headers. Try again after reset if needed.
		rates_remaining, err := strconv.Atoi(resp.Header.Get("RateLimit-Remaining"))
		if err != nil {
			// Gitlab sends rate limit headers only when you hit them or abuse detected?
			//fmt.Printf("[lab_request] Warning: could not parse remaining Gitlab requests number. URL: %s\n", url)
		} else if rates_remaining == 0 {
			rates_reset, err := strconv.ParseInt(resp.Header.Get("RateLimit-Reset"), 10, 64)
			if err != nil {
				fmt.Printf("[lab_request] Warning: could not parse Gitlab requests reset time. URL: %s\n", url)
			} else {
				reset_time := time.Unix(rates_reset, 0)
				sleep_duration := time.Until(reset_time)
				if sleep_duration > 0 {
					fmt.Printf("[lab_request] Rate limit hit. Sleeping till %s.\n", reset_time.Format("2006.01.02 15:04:05"))
					resp.Body.Close()
					time.Sleep(sleep_duration)
					continue
				}
			}
		}

		gitlab_response, err := io.ReadAll(resp.Body)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[lab_request] failed to read response: "+err.Error())
			err_ctr_hb++
			return nil
		}
		(*req_num)++

		return gitlab_response
	}
}

func gitlab_checker(entry *HB_Entry) bool {
	// Getting commits from gitlab
	var entry_rel_arr []lab_release_entry
	err := json.Unmarshal(lab_request(entry.API_url, &lab_req_used), &entry_rel_arr)
	if err != nil {
		error_arr_hb = append(error_arr_hb, "[gitlab_checker] failed to unmarshal gitlab response: "+err.Error())
		err_ctr_hb++
		return false
	}
	// Do nothing if there are no releases
	if len(entry_rel_arr) == 0 {
		return false
	}
	// Sorting tags in descending order
	sort.SliceStable(entry_rel_arr, func(i, j int) bool {
		date1, _ := time.Parse(time.RFC3339, entry_rel_arr[i].Date)
		date2, _ := time.Parse(time.RFC3339, entry_rel_arr[j].Date)
		return date1.After(date2)
	})
	// Check if first tag in array is newer then entry date
	entry_date, _ := time.Parse(time.RFC3339, entry.Commit_date)
	tag_date, _ := time.Parse(time.RFC3339, entry_rel_arr[0].Date)
	if tag_date.After(entry_date) {
		// Updating entry in main array if there is update
		(*entry).HTML_url = entry_rel_arr[0].Links.Release_URL
		(*entry).Commit_date = entry_rel_arr[0].Date
		(*entry).Tag_name = entry_rel_arr[0].Tag_name

		return true
	}

	return false
}

func hub_request(url string, req_num *int) []byte {
	client := &http.Client{}
	for {
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[hub_request] failed to create request: "+err.Error())
			err_ctr_hb++
			return nil
		}
		// Auth headers for 5000 requests per hour
		if github_token != "" {
			req.Header.Add("Authorization", github_token)
			req.Header.Add("Content-Type", "application/json")
		}
		resp, err := client.Do(req)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[hub_request] failed to perform request: "+err.Error())
			err_ctr_hb++
			return nil
		}
		defer resp.Body.Close()

		// Read ratelimits from headers. Try again after reset if needed.
		rates_remaining, err := strconv.Atoi(resp.Header.Get("X-RateLimit-Remaining"))
		if err != nil {
			fmt.Printf("[hub_request] Warning: could not parse remaining Github requests number. URL: %s\n", url)
		} else if rates_remaining == 0 {
			rates_reset, err := strconv.ParseInt(resp.Header.Get("X-RateLimit-Reset"), 10, 64)
			if err != nil {
				fmt.Printf("[hub_request] Warning: could not parse Github requests reset time. URL: %s\n", url)
			} else {
				reset_time := time.Unix(rates_reset, 0)
				sleep_duration := time.Until(reset_time)
				if sleep_duration > 0 {
					fmt.Printf("[hub_request] Rate limit hit. Sleeping till %s.\n", reset_time.Format("2006.01.02 15:04:05"))
					resp.Body.Close()
					time.Sleep(sleep_duration)
					continue
				}
			}
		}

		github_response, err := io.ReadAll(resp.Body)
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[hub_request] failed to read response: "+err.Error())
			err_ctr_hb++
			return nil
		}
		(*req_num)++

		// add '[' and ']' at the beggining and the end if needed
		if github_response[0] != '[' {
			github_response = append([]byte{'['}, github_response...)
			github_response = append(github_response, ']')
		}

		return github_response
	}
}

func github_checker(entry *HB_Entry) bool {
	// Getting releases from github
	var entry_rel_arr []hub_rel_entry
	err := json.Unmarshal(hub_request(entry.API_url+"/releases", &hub_req_used), &entry_rel_arr)
	if err != nil {
		error_arr_hb = append(error_arr_hb, "[github_checker] Entry: "+entry.App_name+": Couldn't unmarshal github response.")
		err_ctr_hb++
		return false
	}
	// Do nothing if there are no releases
	if len(entry_rel_arr) == 0 {
		return false
	}
	// Do nothing if github return message
	if len(entry_rel_arr[0].Message) > 0 {
		error_arr_hb = append(error_arr_hb, "[github_checker] Entry: "+entry.App_name+" with Github message: "+entry_rel_arr[0].Message)
		err_ctr_hb++
		return false
	}
	// Sorting releases in descending order
	sort.SliceStable(entry_rel_arr, func(i, j int) bool {
		date1, _ := time.Parse(time.RFC3339, entry_rel_arr[i].Date)
		date2, _ := time.Parse(time.RFC3339, entry_rel_arr[j].Date)
		return date1.After(date2)
	})
	// Add error if no date available
	if entry_rel_arr[0].Date == "" {
		error_arr_hb = append(error_arr_hb, "[github_checker] Entry: "+entry.App_name+" Failed to get date for last tag.")
		err_ctr_hb++
		return false
	}
	// Check if first release (or any of assets of first release) in array is newer then entry date
	entry_date, _ := time.Parse(time.RFC3339, entry.Commit_date)
	rel_date, _ := time.Parse(time.RFC3339, entry_rel_arr[0].Date)
	var ass_date time.Time
	ass_ind := 0
	if len(entry_rel_arr[0].Assets) > 0 {
		ass_date, _ = time.Parse(time.RFC3339, entry_rel_arr[0].Assets[0].Updated)
		for i, asset := range entry_rel_arr[0].Assets {
			ass_upd, _ := time.Parse(time.RFC3339, asset.Updated)
			if ass_upd.After(ass_date) {
				ass_ind = i
			}
		}
	} else {
		ass_date = rel_date
	}

	if rel_date.After(entry_date) || ass_date.After(entry_date) {
		// Updating entry in main array if there is update
		owner_ind_strt := strings.Index(entry.API_url, "/repos")
		html_tag_url := "https://github.com" + entry.API_url[owner_ind_strt+6:] + "/releases/tag/" + entry_rel_arr[0].Tag_name
		(*entry).HTML_url = html_tag_url
		if ass_date.After(rel_date) {
			(*entry).Commit_date = entry_rel_arr[0].Assets[ass_ind].Updated
		} else {
			(*entry).Commit_date = entry_rel_arr[0].Date
		}
		(*entry).Tag_name = entry_rel_arr[0].Tag_name

		return true
	}

	return false
}

func print_progress() {
	fmt.Printf("[Working] #1: %d/%d #2: %d/%d #3: %d/%d #4: %d/%d #5: %d/%d #6: %d/%d [%d updates][%d errors]\r",
		t1_ctr, t1_ttl, t2_ctr, t2_ttl, t3_ctr, t3_ttl, t4_ctr, t4_ttl, t5_ctr, t5_ttl, t6_ctr, t6_ttl, updates_ctr, err_ctr_hb)
}

func process_list(tctr *int, entry_list *[]HB_Entry, homebrew_updates_array *[9][]HB_Entry, wg *sync.WaitGroup) {
	defer wg.Done()

	// Iterate through entries from homebrew_list.json
	for entry_ctr := range *entry_list {
		var found_update bool = false
		if strings.Contains((*entry_list)[entry_ctr].API_url, "github") {
			found_update = github_checker(&((*entry_list)[entry_ctr]))
		} else if strings.Contains((*entry_list)[entry_ctr].API_url, "gitlab") {
			found_update = gitlab_checker(&((*entry_list)[entry_ctr]))
		}

		if found_update {
			// Adding entry to update array
			switch (*entry_list)[entry_ctr].Category {
			case "DS(i)":
				homebrew_updates_array[0] = append(homebrew_updates_array[0], (*entry_list)[entry_ctr])
			case "3DS/DS(i)":
				homebrew_updates_array[1] = append(homebrew_updates_array[1], (*entry_list)[entry_ctr])
			case "3DS":
				homebrew_updates_array[2] = append(homebrew_updates_array[2], (*entry_list)[entry_ctr])
			case "Switch":
				homebrew_updates_array[3] = append(homebrew_updates_array[3], (*entry_list)[entry_ctr])
			case "Switch2":
				homebrew_updates_array[4] = append(homebrew_updates_array[4], (*entry_list)[entry_ctr])
			case "3DS/DS(i)/Switch":
				homebrew_updates_array[5] = append(homebrew_updates_array[5], (*entry_list)[entry_ctr])
			case "Wii":
				homebrew_updates_array[6] = append(homebrew_updates_array[6], (*entry_list)[entry_ctr])
			case "WiiU":
				homebrew_updates_array[7] = append(homebrew_updates_array[7], (*entry_list)[entry_ctr])
			case "GBA":
				homebrew_updates_array[8] = append(homebrew_updates_array[8], (*entry_list)[entry_ctr])
			default:
				fmt.Println("Category not supported: ", (*entry_list)[entry_ctr].Category)
			}

			updates_ctr++
		}
		*tctr++
		print_progress()
	}
}

func parse_json(path_to_homebrew_list string) []HB_Entry {
	// Read data from local .json file
	jsonFile, err := os.Open(path_to_homebrew_list)
	if err != nil {
		error_arr_hb = append(error_arr_hb, "[parse_json] failed to open .json file with homebrew list")
		err_ctr_hb++
		return nil
	}
	json_body, _ := io.ReadAll(jsonFile)
	jsonFile.Close()

	// Unmarshaling .json data into entry_list array
	var entry_list []HB_Entry
	err = json.Unmarshal(json_body, &entry_list)
	if err != nil {
		error_arr_hb = append(error_arr_hb, "[parse_json] failed to unmarshal .json file with homebrew list")
		err_ctr_hb++
		return nil
	}

	return entry_list
}

func Homebrew_updates(dry_run bool) string {
	// Get execution path. Lists should be in "lists" folder
	exec_path, err := os.Executable()
	if err != nil {
		error_arr_hb = append(error_arr_hb, "[Homebrew_updates] failed to get execution path")
		err_ctr_hb++
		return ""
	}
	exec_path = filepath.Dir(exec_path)
	// Form list of homebrew apps
	entry_list := parse_json(exec_path + "/lists/" + hb_list)
	if entry_list == nil {
		error_arr_hb = append(error_arr_hb, "[Homebrew_updates] failed to parse .json homebrew list")
		err_ctr_hb++
		return ""
	}
	entries_ttl := len(entry_list)
	// Prepare for list splitting
	ttl_threads := 6
	part_len := entries_ttl / ttl_threads
	list_part1, list_part2 := entry_list[:part_len], entry_list[part_len:part_len*2]
	list_part3, list_part4 := entry_list[part_len*2:part_len*3], entry_list[part_len*3:part_len*4]
	list_part5, list_part6 := entry_list[part_len*4:part_len*5], entry_list[part_len*5:]
	t1_ttl, t2_ttl, t3_ttl, t4_ttl, t5_ttl, t6_ttl = part_len, part_len, part_len, part_len, part_len, entries_ttl-part_len*5

	var homebrew_updates_array [9][]HB_Entry
	var wg sync.WaitGroup
	// start goroutines
	wg.Add(ttl_threads)
	go process_list(&t1_ctr, &list_part1, &homebrew_updates_array, &wg)
	go process_list(&t2_ctr, &list_part2, &homebrew_updates_array, &wg)
	go process_list(&t3_ctr, &list_part3, &homebrew_updates_array, &wg)
	go process_list(&t4_ctr, &list_part4, &homebrew_updates_array, &wg)
	go process_list(&t5_ctr, &list_part5, &homebrew_updates_array, &wg)
	go process_list(&t6_ctr, &list_part6, &homebrew_updates_array, &wg)
	wg.Wait()

	fmt.Printf("\n[Done] Used %d Github and %d Gitlab requests\n", hub_req_used, lab_req_used)

	if !dry_run {
		// Reconstructing .json file with new updates
		entry_list = append(list_part1, list_part2...)
		entry_list = append(entry_list, list_part3...)
		entry_list = append(entry_list, list_part4...)
		entry_list = append(entry_list, list_part5...)
		entry_list = append(entry_list, list_part6...)
		json_list, err := json.MarshalIndent(entry_list, "", "  ")
		if err != nil {
			error_arr_hb = append(error_arr_hb, "[Homebrew_updates] failed to indent homebrew list")
			err_ctr_hb++
		} else { // Rewriting .json file
			err = os.WriteFile(exec_path+"/lists/"+hb_list, json_list, 0666)
			if err != nil {
				error_arr_hb = append(error_arr_hb, "[Homebrew_updates] Coudn't write into list_hb.json. Hope you have backup :(")
				err_ctr_hb++
			}
		}
	}

	hb_str := ""
	for index := range homebrew_updates_array {
		if len(homebrew_updates_array[index]) > 0 {
			hb_str += hash_tag_hb + "\n"
			break
		}
	}
	for index := range homebrew_updates_array {
		if len(homebrew_updates_array[index]) <= 0 {
			continue
		} // Skip empty array
		hb_str += "=== " + homebrew_updates_array[index][0].Category + " ===\n"
		for _, array_entry := range homebrew_updates_array[index] {
			hb_str += "-" + array_entry.Prefix + " Оновлення " + array_entry.App_name + " до версії " + array_entry.Tag_name +
				" від " + array_entry.Commit_date[8:10] + "." + array_entry.Commit_date[5:7] + "." + array_entry.Commit_date[:4] + ": " +
				array_entry.HTML_url + " | " + array_entry.Description + "\n"
		}
		hb_str += "\n"
	}

	// Store string in history file
	if !dry_run {
		dt := time.Now()
		fptr, err := os.OpenFile(exec_path+"/history/"+hist_fl_hb, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0644)
		if err == nil {
			_, err = fptr.WriteString("\n" + dt.Format("2006.01.02-15:04") + "\n" + hb_str)
			if err != nil {
				fptr.Close()
				fmt.Println("error:", err)
			}
		} else {
			error_arr_hb = append(error_arr_hb, "[Homebrew_updates] Coudn't write into list_hb.json. Hope you have backup :(")
			err_ctr_hb++
		}
		fptr.Close()
	}

	return hb_str
}
