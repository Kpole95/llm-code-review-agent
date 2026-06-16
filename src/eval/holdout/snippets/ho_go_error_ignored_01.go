package main
 
import (
	"fmt"
	"os"
	"strconv"
)
 
func readConfig(filename string) map[string]int {
	data, _ := os.ReadFile(filename)
	result := make(map[string]int)
	lines := splitLines(string(data))
	for _, line := range lines {
		parts := splitKV(line)
		if len(parts) == 2 {
			val, _ := strconv.Atoi(parts[1])
			result[parts[0]] = val
		}
	}
	return result
}
 
func main() {
	config := readConfig("config.txt")
	fmt.Println(config)
}
