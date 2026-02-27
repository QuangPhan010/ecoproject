const chartData = {
  day: {
    labels: JSON.parse(document.getElementById("day-labels").textContent),
    data: JSON.parse(document.getElementById("day-data").textContent),
  },
  week: {
    labels: JSON.parse(document.getElementById("week-labels").textContent),
    data: JSON.parse(document.getElementById("week-data").textContent),
  },
  month: {
    labels: JSON.parse(document.getElementById("month-labels").textContent),
    data: JSON.parse(document.getElementById("month-data").textContent),
  },
};

if (document.getElementById("picked-labels")) {
  chartData.picked = {
    labels: JSON.parse(document.getElementById("picked-labels").textContent),
    data: JSON.parse(document.getElementById("picked-data").textContent),
  };
}

const ctx = document.getElementById("revenueChart");

const revenueChart = new Chart(ctx, {
  type: "line",
  data: {
    labels: chartData.day.labels,
    datasets: [{
      data: chartData.day.data,
      borderColor: "#257bd2",
      backgroundColor: "rgba(8, 9, 9, 0.7)",
      borderRadius: 6
    }]
  },
  options: {
    plugins: { legend: { display: false } },
    scales: {
      y: {
        ticks: {
          callback: v => v.toLocaleString()
        }
      }
    }
  }
});

document.querySelectorAll(".chart-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".chart-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    const type = btn.dataset.type;
    revenueChart.data.labels = chartData[type].labels;
    revenueChart.data.datasets[0].data = chartData[type].data;
    revenueChart.update();
  });
});

new Chart(
  document.getElementById("statusPieChart"),
  {
    type: "pie",
    data: {
      labels: JSON.parse(document.getElementById("pie-labels").textContent),
      datasets: [{
        data: JSON.parse(document.getElementById("pie-data").textContent),
        backgroundColor: ["#22c55e","#facc15","#3b82f6","#a855f7","#ef4444"]
      }]
    }
  }
);
