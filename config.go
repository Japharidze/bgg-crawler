package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
)

type Configuration struct {
	DOMAIN string
	ROUTE  string
	PAGES  int
}

func GetConfig() Configuration {
	// jsonFile, err := os.Open("config.json")
	jsonFile, err := ioutil.ReadFile("./config.json")

	if err != nil {
		fmt.Println("Config file not loaded!")
	}

	var config Configuration
	json.Unmarshal(jsonFile, &config)

	return config
}
