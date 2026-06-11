import { getMarketOverview } from "./src/services/marketService";
import { useConfigStore } from "./src/stores/useConfigStore";

async function test() {
  try {
    const config = useConfigStore.getState().config;
    console.log("Calling getMarketOverview...");
    const res = await getMarketOverview(config, "A-Share", true, 1);
    console.log("Success:", JSON.stringify(res, null, 2));
  } catch (e) {
    console.error("Error:", e);
  }
}
test();
