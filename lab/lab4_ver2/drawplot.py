import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

CSV_PATH = "metric.csv"
OUT_DIR = "figs"

sns.set(style="whitegrid", context="notebook", font="Arial Unicode MS")

def ensure_outdir():
    os.makedirs(OUT_DIR, exist_ok=True)

def load_data():
    df = pd.read_csv(CSV_PATH)
    # 规范数据类型
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    df["goodput_mbps"] = pd.to_numeric(df["goodput_mbps"], errors="coerce")
    df["utilization"] = pd.to_numeric(df["utilization"], errors="coerce")
    # 便于图例：如 "GBN + Reno" / "SR + Vegas"
    df["label"] = df["arq"].str.upper() + " + " + df["cc"].str.title()
    return df

def plot_lines(df, x, y, hue, title, xlabel, ylabel, filename, markers=True):
    plt.figure(figsize=(7.5, 4.5), dpi=140)
    # 为了稳定的颜色/顺序
    hue_order = sorted(df[hue].unique())
    ax = sns.lineplot(
        data=df.sort_values(by=x),
        x=x, y=y, hue=hue, hue_order=hue_order,
        marker="o" if markers else None
    )
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(title="算法组合", loc="best")
    plt.tight_layout()
    out_path = os.path.join(OUT_DIR, filename)
    plt.savefig(out_path)
    plt.close()

def main():
    ensure_outdir()
    df = load_data()

    # 实验 1：模拟 | GBN/SR + Reno | 丢包率 -> 有效吞吐量
    exp1 = df[(df["var"] == "loss") & (df["cc"] == "reno") & (df["arq"].isin(["gbn", "sr"]))]
    plot_lines(
        exp1, x="val", y="goodput_mbps", hue="label",
        title="实验1（模拟）：GBN/SR + Reno 在不同丢包率下的有效吞吐量",
        xlabel="丢包率（%）", ylabel="有效吞吐量（Mbps）",
        filename="fig1_loss_goodput_gbn_sr_reno.png"
    )

    # 实验 2：模拟 | GBN/SR + Reno | 丢包率 -> 流量利用率
    plot_lines(
        exp1, x="val", y="utilization", hue="label",
        title="实验2（模拟）：GBN/SR + Reno 在不同丢包率下的流量利用率",
        xlabel="丢包率（%）", ylabel="流量利用率",
        filename="fig2_loss_utilization_gbn_sr_reno.png"
    )

    # 实验 3：模拟 | SR + (Reno/Vegas) | 丢包率 -> 有效吞吐量
    exp3 = df[(df["var"] == "loss") & (df["arq"] == "sr") & (df["cc"].isin(["reno", "vegas"]))]
    plot_lines(
        exp3, x="val", y="goodput_mbps", hue="label",
        title="实验3（模拟）：SR + Reno/Vegas 在不同丢包率下的有效吞吐量",
        xlabel="丢包率（%）", ylabel="有效吞吐量（Mbps）",
        filename="fig3_loss_goodput_sr_reno_vs_vegas.png"
    )

    # 实验 4：模拟 | SR + (Reno/Vegas) | 丢包率 -> 流量利用率
    plot_lines(
        exp3, x="val", y="utilization", hue="label",
        title="实验4（模拟）：SR + Reno/Vegas 在不同丢包率下的流量利用率",
        xlabel="丢包率（%）", ylabel="流量利用率",
        filename="fig4_loss_utilization_sr_reno_vs_vegas.png"
    )

    # 实验 5：模拟 | SR + (Reno/Vegas) | 延迟 -> 有效吞吐量
    exp5 = df[(df["var"] == "delay") & (df["arq"] == "sr") & (df["cc"].isin(["reno", "vegas"]))]
    plot_lines(
        exp5, x="val", y="goodput_mbps", hue="label",
        title="实验5（模拟）：SR + Reno/Vegas 在不同时延下的有效吞吐量",
        xlabel="时延（ms）", ylabel="有效吞吐量（Mbps）",
        filename="fig5_delay_goodput_sr_reno_vs_vegas.png"
    )

    # 实验 6：模拟 | SR + (Reno/Vegas) | 延迟 -> 流量利用率
    plot_lines(
        exp5, x="val", y="utilization", hue="label",
        title="实验6（模拟）：SR + Reno/Vegas 在不同时延下的流量利用率",
        xlabel="时延（ms）", ylabel="流量利用率",
        filename="fig6_delay_utilization_sr_reno_vs_vegas.png"
    )

    # 实验 7：真实 | GBN/SR + Reno | 上传文件大小 -> 有效吞吐量
    exp7 = df[(df["var"] == "size_kb") & (df["cc"] == "reno") & (df["arq"].isin(["gbn", "sr"]))]
    plot_lines(
        exp7, x="val", y="goodput_mbps", hue="label",
        title="实验7（真实）：GBN/SR + Reno 随文件大小的有效吞吐量",
        xlabel="文件大小（KB）", ylabel="有效吞吐量（Mbps）",
        filename="fig7_size_goodput_gbn_vs_sr_reno.png"
    )

    # 实验 8：真实 | GBN/SR + Reno | 上传文件大小 -> 流量利用率
    plot_lines(
        exp7, x="val", y="utilization", hue="label",
        title="实验8（真实）：GBN/SR + Reno 随文件大小的流量利用率",
        xlabel="文件大小（KB）", ylabel="流量利用率",
        filename="fig8_size_utilization_gbn_vs_sr_reno.png"
    )

    # 实验 9：真实 | SR + (Reno/Vegas) | 文件大小 -> 有效吞吐量
    exp9 = df[(df["var"] == "size_kb") & (df["arq"] == "sr") & (df["cc"].isin(["reno", "vegas"]))]
    plot_lines(
        exp9, x="val", y="goodput_mbps", hue="label",
        title="实验9（真实）：SR + Reno/Vegas 随文件大小的有效吞吐量",
        xlabel="文件大小（KB）", ylabel="有效吞吐量（Mbps）",
        filename="fig9_size_goodput_sr_reno_vs_vegas.png"
    )

    # 实验 10：真实 | SR + (Reno/Vegas) | 文件大小 -> 流量利用率
    plot_lines(
        exp9, x="val", y="utilization", hue="label",
        title="实验10（真实）：SR + Reno/Vegas 随文件大小的流量利用率",
        xlabel="文件大小（KB）", ylabel="流量利用率",
        filename="fig10_size_utilization_sr_reno_vs_vegas.png"
    )

    print(f"图像已输出到: {os.path.abspath(OUT_DIR)}")

if __name__ == "__main__":
    main()