import { CompanyDetailView } from '@/components/CompanyDetail';

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CompanyDetailView companyId={id} />;
}
