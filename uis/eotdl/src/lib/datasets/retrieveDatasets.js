import { EOTDL_API } from '$lib/env';

export default async (fetch, limit=null) => {
	let url = `${EOTDL_API}/datasets`;
  if (limit) url += `?limit=${limit}`;
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (res.status == 200) 
      return data
    throw new Error(data.message)
  } catch (err) {
    return []
  }
};
