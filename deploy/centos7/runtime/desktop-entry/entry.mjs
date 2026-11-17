import { app } from "electron";
app.setAppPath("/home/verification-agent/zcode/packages/desktop");
await import("/home/verification-agent/zcode/packages/desktop/out/main/index.js");
