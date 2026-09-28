import { Navigate, Route, Routes } from "react-router-dom"
import { Shell } from "@/components/Shell"
import { Review } from "@/pages/Review"
import { Niches } from "@/pages/Niches"
import { Budget } from "@/pages/Budget"

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/review" replace />} />
        <Route path="/review" element={<Review />} />
        <Route path="/niches" element={<Niches />} />
        <Route path="/budget" element={<Budget />} />
        <Route path="*" element={<Navigate to="/review" replace />} />
      </Route>
    </Routes>
  )
}
