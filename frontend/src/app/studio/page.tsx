import { redirect } from 'next/navigation';

export default function StudioPage() {
  redirect('/workspace?agent=studio');
}
