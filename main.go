package main

import (
	"fmt"
)

func main() {
	fmt.Print("Started ...")
	bgs := CrawlLinks()
	fmt.Println(bgs[0])
}
