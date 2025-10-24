import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ApiError, OpenAPI } from "./client"
import { CustomProvider } from "./components/ui/provider"
import { routeTree } from "./routeTree.gen"
import axios from "axios"

OpenAPI.BASE = import.meta.env.VITE_API_URL
OpenAPI.WITH_CREDENTIALS = true
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}

OpenAPI.interceptors.response.use(async (response) => {
  if (response.status === 401) {
    try {
      const refreshResp = await axios.post(`${OpenAPI.BASE}/api/v1/auth/refresh`, null, {
        withCredentials: true,
      })
      if (refreshResp.status >= 200 && refreshResp.status < 300) {
        const { access_token } = refreshResp.data as { access_token: string }
        localStorage.setItem("access_token", access_token)
        const original = response.config
        if (original) {
          const headers = original.headers ?? {}
          headers["Authorization"] = `Bearer ${access_token}`
          original.headers = headers
          original.withCredentials = OpenAPI.WITH_CREDENTIALS
          return await axios.request(original)
        }
      }
    } catch (e) {
      localStorage.removeItem("access_token")
      window.location.href = "/login"
    }
  }
  return response
})
const handleApiError = (error: Error) => {
  if (error instanceof ApiError && [401, 403].includes(error.status)) {
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  }
}
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <CustomProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </CustomProvider>
  </StrictMode>,
)
