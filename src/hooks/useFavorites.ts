import { useCallback, useEffect, useState } from 'react'
import { listFavorites, type FavoriteItem } from '../api/agent'

export function useGlobalFavorites() {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const items = await listFavorites()
      setFavorites(items)
    } catch {
      setFavorites([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { favorites, isLoading, refresh }
}
