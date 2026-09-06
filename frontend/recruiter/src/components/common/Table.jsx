import './Table.css';
export default function Table({ headers, data, renderRow }) {
  return (
    <div className="table-container">
      <table className="table">
        <thead>
          <tr>{headers.map((h, i) => <th key={i}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {data.length > 0 ? data.map((row, i) => renderRow(row, i)) : <tr><td colSpan={headers.length} className="text-center">No data available</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
