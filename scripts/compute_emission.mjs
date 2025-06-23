import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const inputDataPath = path.join(__dirname, "../data/lh_data_got.json");
const outputEmissionPath = path.join(__dirname, "../data/carbon_emission.json");

function calculateCarbonEmissions(totalBytes) {
  const bytesToGB = totalBytes / 1024 ** 3;
  const energyPerGB = 0.055 + 0.059;
  const carbonIntensity = 494;
  const dataTransferEmissions = bytesToGB * energyPerGB * carbonIntensity;

  const userPowerConsumption = 0.076;
  const userTimeHours = 50 / 3600;
  const userDeviceEmissions = userPowerConsumption * userTimeHours * carbonIntensity;

  return dataTransferEmissions + userDeviceEmissions;
}

async function computeCarbonEmission() {
  try {
    const data = await fs.readFile(inputDataPath, "utf-8");
    const jsonData = JSON.parse(data);

    /*if (!jsonData.total_byte_weight) {
      console.error("❌ 无法找到 total_byte_weight 数据！");
      return;
    }*/
     if (!jsonData.total_byte_weight || jsonData.total_byte_weight <= 0) {
      console.error("❌ total_byte_weight 数据缺失或无效！");
      return;
    }

    const totalBytes = jsonData.total_byte_weight;
    const carbonEmissions = calculateCarbonEmissions(totalBytes);

    const carbonEmissionData = {
      total_byte_weight: totalBytes,
      carbon_emissions: carbonEmissions,
    };

    await fs.writeFile(outputEmissionPath, JSON.stringify(carbonEmissionData, null, 2));
    console.log("✅ 碳排放数据已计算并写入 carbon_emission.json");
  } catch (err) {
    console.error("❌ 计算碳排放时出错！", err);
  }
}

computeCarbonEmission();

