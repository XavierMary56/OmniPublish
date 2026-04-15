import axios, { AxiosResponse, InternalAxiosRequestConfig } from "axios";

import { generateOauthId } from "./utilities";
import { decryptData, encryptData } from "./common";
import { useProjectStore } from "@/stores/project";
import { useAuthStore } from "@/stores/auth";

const defaultList = [
  "https://bpi5.ynrwkze.cc/api.php",
];

const baseApi = defaultList[Math.floor(Math.random() * defaultList.length)];

function setInterceptors(axiosInstance: {
  interceptors: {
    request: {
      use: (
        arg0: (
          config: InternalAxiosRequestConfig
        ) => InternalAxiosRequestConfig<any>,
        arg1: (error: any) => Promise<never>
      ) => void;
    };
    response: {
      use: (
        arg0: (response: AxiosResponse) => any,
        arg1: (error: any) => Promise<never>
      ) => void;
    };
  };
}) {
  // 请求拦截器
  axiosInstance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      // 在请求之前做些什么，比如添加 token 和其他参数
      let token: string | null = null;
      if (config.url != "/api/remote/project_list") {
        token = sessionStorage.getItem("auth_token");
      }
      // 只处理 POST 请求
      if (config.method === "post") {
        const oauthId = generateOauthId();
        const projectStore = useProjectStore();
        const version = projectStore.currentProject?.version ?? "1.0.0";

        // 基础请求参数
        const baseRequestParams = {
          oauth_id: oauthId,
          bundleId: "com.pc.jyaw",
          version,
          oauth_type: "web",
          language: "zh",
          via: "web",
          token,
        };

        // 保存 oauth_id 到本地存储
        sessionStorage.setItem("__public_oauth_id__", oauthId);

        // 合并请求数据
        const requestData = config.data
          ? { ...baseRequestParams, ...config.data }
          : baseRequestParams;
        console.log(requestData, "@@@请求参数");
        // 加密处理
        config.data = encryptData(JSON.stringify(requestData));
      }

      return config;
    },
    (error: any) => {
      return Promise.reject(error);
    }
  );

  // 响应拦截器
  axiosInstance.interceptors.response.use(
    (response: AxiosResponse) => {
      if (response.data != null && response.data.data != null) {
        response.data = decryptData(response.data.data);
        const data = JSON.parse(response.data);
        console.log(data, "###返回参数");
        const authStore = useAuthStore();
        if (
          data.msg &&
          (String(data.msg).includes("token无效") ||
            String(data.msg).includes("TOKEN失效") ||
            String(data.msg).includes("未登录"))
        ) {
          authStore.logout();
        }
      }

      return JSON.parse(response.data);
    },
    (error: { code: string; message: string | string[] }) => {
      return Promise.reject(error);
    }
  );
}

function baseAxiod() {
  const defaultAxios = axios.create({
    baseURL: baseApi,
    timeout: 10000,
  });
  setInterceptors(defaultAxios);
  return defaultAxios;
}

const apiCache: Record<string, string> = {};

function createCustomAxios() {
  const project = useProjectStore();
  const apis = project.currentProject?.api ?? [];
  const projectType = project.currentProject?.type ?? "default";

  if (!apiCache[projectType]) {
    apiCache[projectType] = apis[Math.floor(Math.random() * apis.length)];
  }

  const customInstance = axios.create({
    baseURL: apiCache[projectType],
    timeout: 60000,
  });
  setInterceptors(customInstance);
  return customInstance;
}

export { baseAxiod, createCustomAxios, setInterceptors };
