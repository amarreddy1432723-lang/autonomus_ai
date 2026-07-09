import { redirect } from 'next/navigation';

export default function InternetPage() {
  redirect('/workspace?agent=research');
}
