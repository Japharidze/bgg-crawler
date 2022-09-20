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
	link   string
	name   string
	price  float32
	rating string
}

func CrawlLinks() []BG {
	var bgs []BG
	c := colly.NewCollector(
		colly.AllowedDomains(domain),
		colly.UserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"),
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

	for i := 0; i < len(bgs); i++ {
		parseOne(&bgs[i], c)
		break
	}

	return bgs
}

func parseOne(bg *BG, c *colly.Collector) {
	c.OnRequest(func(r *colly.Request) {
		fmt.Println("Visiting single BG")
		fmt.Println(r.Headers)
	})

	c.OnResponse(func(r *colly.Response) {
		fmt.Println(r.Ctx.Get("age"))
		r.Ctx.ForEach(func(k string, _ interface{}) interface{} {
			fmt.Println(k)
			return nil
		})
	})

	c.OnHTML("div.rating-overall", func(e *colly.HTMLElement) {
		fmt.Println("Found!", e)
	})

	c.Visit(bg.link)
}
