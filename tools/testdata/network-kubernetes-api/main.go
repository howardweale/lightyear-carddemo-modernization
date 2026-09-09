// Exercise Kubernetes' actual typed JSON representation, including omitempty
// and resource.Quantity serialization, without contacting a cluster.
package main

import (
	"encoding/json"
	"os"

	corev1 "k8s.io/api/core/v1"
)

func main() {
	var pod corev1.Pod
	if err := json.NewDecoder(os.Stdin).Decode(&pod); err != nil {
		os.Exit(2)
	}
	if err := json.NewEncoder(os.Stdout).Encode(pod); err != nil {
		os.Exit(3)
	}
}
