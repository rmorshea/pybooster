import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

mermaid.registerIconPacks([
    {
        name: "simple-icons",
        loader: () =>
            fetch("https://unpkg.com/@iconify-json/logos/icons.json").then((res) =>
                res.json()
            ),
    },
]);
