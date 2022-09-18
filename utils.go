package main

import (
	"fmt"

	"github.com/gocolly/colly"
)

var link_selector string = `a.primary`
var config Configuration = GetConfig()
var domain string = config.DOMAIN
var route string = config.ROUTE

type BG struct {
	link  string
	name  string
	price float32
}

func CrawlLinks() []BG {
	var bgs []BG
	c := colly.NewCollector(
		colly.AllowedDomains(domain),
	)
	c.OnRequest(func(r *colly.Request) {
		fmt.Println("Visiting", r.URL)
	})
	c.OnResponse(func(r *colly.Response) {
		fmt.Println("Response Code: ", r.StatusCode)
	})
	c.OnError(func(_ *colly.Response, err error) {
		fmt.Println("Error : ", err)
	})
	c.OnHTML(link_selector, func(e *colly.HTMLElement) {
		bg := BG{}
		link := e.Attr(`href`)
		link = fmt.Sprintf("https://%s%s", domain, link)
		bg.link = link
		bgs = append(bgs, bg)
	})
	c.Visit(fmt.Sprintf("https://%s/%s/1", domain, route))

	for _, bg := range bgs {
		parseOne(&bg, c)
		break
	}

	return bgs
}

func parseOne(bg *BG, c *colly.Collector) {
	c.OnRequest(func(r *colly.Request) {
		fmt.Println("Visiting single BG")
	})

	c.OnHTML("a", func(r *colly.HTMLElement) {
		bg.price = 10
	})
	c.Visit(bg.link)
	fmt.Println("Bug here", bg)
}
